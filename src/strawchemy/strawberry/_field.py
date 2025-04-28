from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from functools import cached_property
from inspect import isclass
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Optional,
    Self,
    TypeAlias,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    override,
)

from typing_extensions import TypeIs

from strawberry.annotation import StrawberryAnnotation
from strawberry.types import get_object_definition
from strawberry.types.arguments import StrawberryArgument
from strawberry.types.base import StrawberryList, StrawberryOptional, StrawberryType, WithStrawberryObjectDefinition
from strawberry.types.field import UNRESOLVED, StrawberryField
from strawchemy.dto.types import DTOConfig, Purpose
from strawchemy.exceptions import InputValidationError
from strawchemy.graphql.constants import (
    DATA_KEY,
    DISTINCT_ON_KEY,
    FILTER_KEY,
    LIMIT_KEY,
    NODES_KEY,
    OFFSET_KEY,
    ORDER_BY_KEY,
)
from strawchemy.graphql.dto import (
    BooleanFilterDTO,
    EnumDTO,
    MappedDataclassGraphQLDTO,
    MappedPydanticGraphQLDTO,
    OrderByDTO,
    StrawchemyDTOAttributes,
)
from strawchemy.input import Input
from strawchemy.strawberry.types import ValidationErrorType
from strawchemy.strawberry.typing import StrawchemyTypeWithStrawberryObjectDefinition
from strawchemy.types import DefaultOffsetPagination
from strawchemy.utils import is_type_hint_optional

from ._utils import dto_model_from_type, strawberry_contained_types, strawberry_contained_user_type
from .exceptions import StrawchemyFieldError
from .repository import StrawchemyAsyncRepository

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine, Mapping

    from sqlalchemy import Select
    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
    from strawberry import BasePermission, Info
    from strawberry.extensions.field_extension import FieldExtension
    from strawberry.types.base import StrawberryObjectDefinition, StrawberryType, WithStrawberryObjectDefinition
    from strawberry.types.fields.resolver import StrawberryResolver
    from strawchemy.dto.backend.pydantic import MappedPydanticDTO
    from strawchemy.dto.base import ModelInspector
    from strawchemy.graphql.dto import BooleanFilterDTO, EnumDTO, OrderByDTO
    from strawchemy.graphql.typing import AnyMappedDTO, MappedGraphQLDTO
    from strawchemy.sqlalchemy.typing import QueryHookCallable
    from strawchemy.typing import AnyRepository

    from .repository import StrawchemySyncRepository
    from .typing import (
        AnySessionGetter,
        FilterStatementCallable,
        StrawchemyTypeFromPydantic,
        StrawchemyTypeWithStrawberryObjectDefinition,
    )


__all__ = ("StrawchemyCreateMutationField", "StrawchemyDeleteMutationField", "StrawchemyField")

T = TypeVar("T", bound="DeclarativeBase")

ListResolverResult: TypeAlias = (
    "Sequence[StrawchemyTypeWithStrawberryObjectDefinition] | StrawchemyTypeWithStrawberryObjectDefinition"
)
GetByIdResolverResult: TypeAlias = "StrawchemyTypeWithStrawberryObjectDefinition | None"
CreateOrUpdateResolverResult: TypeAlias = (
    "Sequence[StrawchemyTypeWithStrawberryObjectDefinition] | ValidationErrorType | Sequence[ValidationErrorType]"
)


_OPTIONAL_UNION_ARG_SIZE: int = 2


def _is_list(
    type_: StrawberryType | type[WithStrawberryObjectDefinition] | object | str,
) -> TypeIs[type[list[Any]] | StrawberryList]:
    if isinstance(type_, StrawberryOptional):
        type_ = type_.of_type
    if origin := get_origin(type_):
        type_ = origin
        if origin is Optional:
            type_ = get_args(type_)[0]
        if origin in (Union, UnionType) and len(args := get_args(type_)) == _OPTIONAL_UNION_ARG_SIZE:
            type_ = args[0] if args[0] is not type(None) else args[1]

    return isinstance(type_, StrawberryList) or type_ is list


class StrawchemyField(StrawberryField):
    """A custom field class for Strawberry GraphQL that allows explicit handling of resolver arguments.

    This class extends the default Strawberry field functionality by allowing the
    specification of a list of arguments that the resolver function accepts, instead of pulling them from the function signature.
    This is useful for scenarios where you want to have fine-grained control over the resolver
    arguments or when integrating with other systems that require explicit argument
    definitions.

    Attributes:
        arguments: A list of StrawberryArgument instances representing the arguments
                   that the resolver function accepts.
    """

    @override
    def __init__(
        self,
        inspector: ModelInspector[Any, Any],
        session_getter: AnySessionGetter,
        repository_type: AnyRepository,
        filter_type: type[StrawchemyTypeFromPydantic[BooleanFilterDTO[T, QueryableAttribute[Any]]]] | None = None,
        order_by: type[StrawchemyTypeFromPydantic[OrderByDTO[T, QueryableAttribute[Any]]]] | None = None,
        distinct_on: type[EnumDTO] | None = None,
        pagination: bool | DefaultOffsetPagination = False,
        root_aggregations: bool = False,
        auto_snake_case: bool = True,
        registry_namespace: dict[str, Any] | None = None,
        filter_statement: FilterStatementCallable | None = None,
        query_hook: QueryHookCallable[Any] | Sequence[QueryHookCallable[Any]] | None = None,
        execution_options: dict[str, Any] | None = None,
        id_field_name: str = "id",
        # Original StrawberryField args
        python_name: str | None = None,
        graphql_name: str | None = None,
        type_annotation: StrawberryAnnotation | None = None,
        origin: type | Callable[..., Any] | staticmethod[Any, Any] | classmethod[Any, Any, Any] | None = None,
        is_subscription: bool = False,
        description: str | None = None,
        base_resolver: StrawberryResolver[Any] | None = None,
        permission_classes: list[type[BasePermission]] = (),  # pyright: ignore[reportArgumentType]
        default: object = dataclasses.MISSING,
        default_factory: Callable[[], Any] | object = dataclasses.MISSING,
        metadata: Mapping[Any, Any] | None = None,
        deprecation_reason: str | None = None,
        directives: Sequence[object] = (),
        extensions: list[FieldExtension] = (),  # pyright: ignore[reportArgumentType]
        root_field: bool = False,
    ) -> None:
        self.type_annotation = type_annotation
        self.registry_namespace = registry_namespace
        self.is_root_field = root_field
        self.inspector = inspector
        self.auto_snake_case = auto_snake_case
        self.root_aggregations = root_aggregations
        self.distinct_on = distinct_on
        self.query_hook = query_hook
        self.pagination: DefaultOffsetPagination | Literal[False] = (
            DefaultOffsetPagination() if pagination is True else pagination
        )
        self.id_field_name = id_field_name

        self._filter = filter_type
        self._order_by = order_by
        self._description = description
        self._session_getter = session_getter
        self._filter_statement = filter_statement
        self._execution_options = execution_options

        self._repository_type = repository_type

        super().__init__(
            python_name,
            graphql_name,
            type_annotation,
            origin,
            is_subscription,
            description,
            base_resolver,
            permission_classes,
            default,
            default_factory,
            metadata,
            deprecation_reason,
            directives,
            extensions,
        )

    def _type_or_annotation(self) -> StrawberryType | type[WithStrawberryObjectDefinition] | object | str:
        type_ = self.type
        if type_ is UNRESOLVED and self.type_annotation:
            type_ = self.type_annotation.annotation
        return type_

    @property
    def _strawchemy_type(self) -> type[StrawchemyTypeWithStrawberryObjectDefinition]:
        return cast("type[StrawchemyTypeWithStrawberryObjectDefinition]", self.type)

    def _get_repository(self, info: Info[Any, Any]) -> StrawchemySyncRepository[Any] | StrawchemyAsyncRepository[Any]:
        return self._repository_type(
            self._strawchemy_type,
            session=self._session_getter(info),  # pyright: ignore[reportArgumentType]
            info=info,
            auto_snake_case=self.auto_snake_case,
            root_aggregations=self.root_aggregations,
            filter_statement=self.filter_statement(info),
            execution_options=self._execution_options,
        )

    def _get_by_id_resolver(
        self, info: Info, **kwargs: Any
    ) -> GetByIdResolverResult | Coroutine[GetByIdResolverResult, Any, Any]:
        repository = self._get_repository(info)
        return repository.get_by_id(strict=not self.is_optional, **kwargs)

    def _list_resolver(
        self,
        info: Info,
        filter_input: StrawchemyTypeFromPydantic[BooleanFilterDTO[T, QueryableAttribute[Any]]] | None = None,
        order_by: list[StrawchemyTypeFromPydantic[OrderByDTO[T, QueryableAttribute[Any]]]] | None = None,
        distinct_on: list[EnumDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> ListResolverResult | Coroutine[ListResolverResult, Any, Any]:
        repository = self._get_repository(info)
        return repository.list(filter_input, order_by, distinct_on, limit, offset)

    def _validate_type(self, type_: StrawberryType | type[WithStrawberryObjectDefinition] | Any) -> None:
        for inner_type in strawberry_contained_types(type_):
            if (
                self.root_aggregations
                and issubclass(inner_type, StrawchemyDTOAttributes)
                and not inner_type.__strawchemy_is_root_aggregation_type__
            ):
                msg = f"The `{self.name}` field is defined with `root_aggregations` enabled but the field type is not a root aggregation type."
                raise StrawchemyFieldError(msg)

    @classmethod
    def _is_strawchemy_type(
        cls, type_: Any
    ) -> TypeIs[MappedDataclassGraphQLDTO[Any] | type[MappedDataclassGraphQLDTO[Any]]]:
        return isinstance(type_, MappedDataclassGraphQLDTO) or (
            isclass(type_) and issubclass(type_, MappedDataclassGraphQLDTO)
        )

    @cached_property
    def filter(
        self,
    ) -> type[StrawchemyTypeFromPydantic[BooleanFilterDTO[Any, QueryableAttribute[Any]]]] | None:
        inner_type = strawberry_contained_user_type(self.type)
        if self._filter is None and self._is_strawchemy_type(inner_type):
            return inner_type.__strawchemy_filter__
        return self._filter

    @cached_property
    def order_by(self) -> type[StrawchemyTypeFromPydantic[OrderByDTO[Any, QueryableAttribute[Any]]]] | None:
        inner_type = strawberry_contained_user_type(self.type)
        if self._order_by is None and self._is_strawchemy_type(inner_type):
            return inner_type.__strawchemy_order_by__
        return self._order_by

    def auto_arguments(self) -> list[StrawberryArgument]:
        arguments: list[StrawberryArgument] = []
        inner_type = strawberry_contained_user_type(self.type)

        if self.is_list:
            if self.pagination:
                arguments.extend(
                    [
                        StrawberryArgument(
                            LIMIT_KEY,
                            None,
                            type_annotation=StrawberryAnnotation(int | None),
                            default=self.pagination.limit,
                        ),
                        StrawberryArgument(
                            OFFSET_KEY,
                            None,
                            type_annotation=StrawberryAnnotation(int),
                            default=self.pagination.offset,
                        ),
                    ]
                )
            if self.filter:
                arguments.append(
                    StrawberryArgument(
                        python_name="filter_input",
                        graphql_name=FILTER_KEY,
                        type_annotation=StrawberryAnnotation(self.filter | None),
                        default=None,
                    )
                )
            if self.order_by:
                arguments.append(
                    StrawberryArgument(
                        ORDER_BY_KEY,
                        None,
                        type_annotation=StrawberryAnnotation(list[self.order_by] | None),
                        default=None,
                    )
                )
            if self.distinct_on:
                arguments.append(
                    StrawberryArgument(
                        DISTINCT_ON_KEY,
                        None,
                        type_annotation=StrawberryAnnotation(list[self.distinct_on] | None),
                        default=None,
                    )
                )
        elif issubclass(inner_type, MappedDataclassGraphQLDTO | MappedPydanticGraphQLDTO):
            model = dto_model_from_type(inner_type)
            id_fields = list(self.inspector.id_field_definitions(model, DTOConfig(Purpose.READ)))
            if len(id_fields) == 1:
                field = id_fields[0][1]
                arguments.append(
                    StrawberryArgument(self.id_field_name, None, type_annotation=StrawberryAnnotation(field.type_))
                )
            else:
                arguments.extend(
                    [
                        StrawberryArgument(name, None, type_annotation=StrawberryAnnotation(field.type_))
                        for name, field in self.inspector.id_field_definitions(model, DTOConfig(Purpose.READ))
                    ]
                )
        return arguments

    def filter_statement(self, info: Info[Any, Any]) -> Select[tuple[DeclarativeBase]] | None:
        return self._filter_statement(info) if self._filter_statement else None

    @cached_property
    def is_list(self) -> bool:
        return True if self.root_aggregations else _is_list(self._type_or_annotation())

    @cached_property
    def is_optional(self) -> bool:
        type_ = self._type_or_annotation()
        return isinstance(type_, StrawberryOptional) or is_type_hint_optional(type_)

    @property
    @override
    def is_basic_field(self) -> bool:
        return not self.is_root_field

    @cached_property
    @override
    def is_async(self) -> bool:
        return issubclass(self._repository_type, StrawchemyAsyncRepository)

    @override
    def __copy__(self) -> Self:
        new_field = type(self)(
            python_name=self.python_name,
            graphql_name=self.graphql_name,
            type_annotation=self.type_annotation,
            origin=self.origin,
            is_subscription=self.is_subscription,
            description=self.description,
            base_resolver=self.base_resolver,
            permission_classes=(self.permission_classes[:] if self.permission_classes is not None else []),  # pyright: ignore[reportUnnecessaryComparison]
            default=self.default_value,
            default_factory=self.default_factory,
            metadata=self.metadata.copy() if self.metadata is not None else None,  # pyright: ignore[reportUnnecessaryComparison]
            deprecation_reason=self.deprecation_reason,
            directives=self.directives[:] if self.directives is not None else [],  # pyright: ignore[reportUnnecessaryComparison]
            extensions=self.extensions[:] if self.extensions is not None else [],  # pyright: ignore[reportUnnecessaryComparison]
            session_getter=self._session_getter,
            filter_statement=self._filter_statement,
            query_hook=self.query_hook,
            id_field_name=self.id_field_name,
            repository_type=self._repository_type,
            inspector=self.inspector,
            auto_snake_case=self.auto_snake_case,
            root_aggregations=self.root_aggregations,
            filter_type=self._filter,
            order_by=self._order_by,
            distinct_on=self.distinct_on,
            pagination=self.pagination,
            registry_namespace=self.registry_namespace,
            execution_options=self._execution_options,
        )
        new_field._arguments = self._arguments[:] if self._arguments is not None else None  # noqa: SLF001
        return new_field

    @property
    @override
    def type(self) -> StrawberryType | type[WithStrawberryObjectDefinition] | Literal[UNRESOLVED]:  # pyright: ignore[reportInvalidTypeForm, reportUnknownParameterType]
        return super().type

    @type.setter
    def type(self, type_: Any) -> None:
        # Ensure type can only be narrowed
        current_annotation = self.type_annotation.annotation if self.type_annotation else UNRESOLVED
        if type_ is UNRESOLVED and current_annotation is not UNRESOLVED:
            return
        self.type_annotation = StrawberryAnnotation.from_annotation(type_, namespace=self.registry_namespace)

    @property
    @override
    def description(self) -> str | None:
        if self._description is not None:
            return self._description
        definition = get_object_definition(strawberry_contained_user_type(self.type), strict=False)
        named_template = "Fetch {object} from the {name} collection"
        if not definition or definition.is_input:
            return None
        if not self.is_list:
            description = named_template.format(object="object", name=definition.name)
            return description if self.base_resolver else f"{description} by id"
        if self.root_aggregations:
            nodes_field = next(field for field in definition.fields if field.python_name == NODES_KEY)
            definition = get_object_definition(strawberry_contained_user_type(nodes_field.type), strict=True)
            return named_template.format(object="aggregation data", name=definition.name)
        return named_template.format(object="objects", name=definition.name)

    @description.setter
    def description(self, value: str) -> None:  # pyright: ignore[reportIncompatibleVariableOverride]
        self._description = value

    @property
    @override
    def arguments(self) -> list[StrawberryArgument]:
        if self.base_resolver:
            return super().arguments
        if not self._arguments:
            self._arguments = self.auto_arguments()
        return self._arguments

    @arguments.setter
    def arguments(self, value: list[StrawberryArgument]) -> None:
        args_prop = super(StrawchemyField, self.__class__).arguments
        return args_prop.fset(self, value)  # pyright: ignore[reportAttributeAccessIssue]

    @override
    def resolve_type(
        self, *, type_definition: StrawberryObjectDefinition | None = None
    ) -> StrawberryType | type[WithStrawberryObjectDefinition] | Any:
        type_ = super().resolve_type(type_definition=type_definition)
        self._validate_type(type_)
        return type_

    def resolver(
        self, info: Info[Any, Any], *args: Any, **kwargs: Any
    ) -> (
        ListResolverResult
        | Coroutine[ListResolverResult, Any, Any]
        | GetByIdResolverResult
        | Coroutine[GetByIdResolverResult, Any, Any]
        | CreateOrUpdateResolverResult
        | Coroutine[CreateOrUpdateResolverResult, Any, Any]
    ):
        if self.is_list:
            return self._list_resolver(info, *args, **kwargs)
        return self._get_by_id_resolver(info, *args, **kwargs)

    @override
    def get_result(
        self, source: Any, info: Info[Any, Any] | None, args: list[Any], kwargs: dict[str, Any]
    ) -> Awaitable[Any] | Any:
        if self.is_root_field and self.base_resolver is None:
            assert info
            return self.resolver(info, *args, **kwargs)
        return super().get_result(source, info, args, kwargs)


class _StrawchemyInputMutationField(StrawchemyField):
    def __init__(
        self,
        input_type: type[MappedGraphQLDTO[T]],
        *args: Any,
        validation: type[MappedPydanticDTO[T]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.is_root_field = True
        self._input_type = input_type
        self._validation_type = validation


class StrawchemyCreateMutationField(_StrawchemyInputMutationField):
    def _create_resolver(
        self, info: Info, data: AnyMappedDTO | Sequence[AnyMappedDTO]
    ) -> CreateOrUpdateResolverResult | Coroutine[CreateOrUpdateResolverResult, Any, Any]:
        repository = self._get_repository(info)
        try:
            return (
                repository.create_many(Input(data, self._validation_type))
                if isinstance(data, Sequence)
                else repository.create(Input(data, self._validation_type))
            )
        except InputValidationError as error:
            return ValidationErrorType.from_pydantic(error.pydantic_error)

    @override
    def auto_arguments(self) -> list[StrawberryArgument]:
        if self.is_list:
            return [StrawberryArgument(DATA_KEY, None, type_annotation=StrawberryAnnotation(list[self._input_type]))]
        return [StrawberryArgument(DATA_KEY, None, type_annotation=StrawberryAnnotation(self._input_type))]

    @override
    def resolver(
        self, info: Info[Any, Any], *args: Any, **kwargs: Any
    ) -> CreateOrUpdateResolverResult | Coroutine[CreateOrUpdateResolverResult, Any, Any]:
        return self._create_resolver(info, *args, **kwargs)


class StrawchemyUpdateMutationField(_StrawchemyInputMutationField):
    @override
    def _validate_type(self, type_: StrawberryType | type[WithStrawberryObjectDefinition] | Any) -> None:
        if self._filter is not None and not _is_list(type_):
            msg = f"Type of update mutation by filter must be a list: {self.name}"
            raise StrawchemyFieldError(msg)

    def _update_by_ids_resolver(
        self, info: Info, data: AnyMappedDTO | Sequence[AnyMappedDTO]
    ) -> CreateOrUpdateResolverResult | Coroutine[CreateOrUpdateResolverResult, Any, Any]:
        repository = self._get_repository(info)
        list_input = isinstance(data, Sequence)
        try:
            return (
                repository.update_many_by_id(Input(data, self._validation_type))
                if list_input
                else repository.update_by_id(Input(data, self._validation_type))
            )
        except InputValidationError as error:
            error = ValidationErrorType.from_pydantic(error.pydantic_error)
            return [error] if list_input else error

    def _update_by_filter_resolver(
        self,
        info: Info,
        data: AnyMappedDTO,
        filter_input: StrawchemyTypeFromPydantic[BooleanFilterDTO[T, QueryableAttribute[Any]]],
    ) -> CreateOrUpdateResolverResult | Coroutine[CreateOrUpdateResolverResult, Any, Any]:
        repository = self._get_repository(info)
        try:
            return repository.update_by_filter(Input(data, self._validation_type), filter_input)
        except InputValidationError as error:
            return [ValidationErrorType.from_pydantic(error.pydantic_error)]

    @override
    def auto_arguments(self) -> list[StrawberryArgument]:
        if self.filter:
            return [
                StrawberryArgument(DATA_KEY, None, type_annotation=StrawberryAnnotation(self._input_type)),
                StrawberryArgument(
                    python_name="filter_input",
                    graphql_name=FILTER_KEY,
                    type_annotation=StrawberryAnnotation(self.filter | None),
                    default=None,
                ),
            ]
        if self.is_list:
            return [StrawberryArgument(DATA_KEY, None, type_annotation=StrawberryAnnotation(list[self._input_type]))]
        return [StrawberryArgument(DATA_KEY, None, type_annotation=StrawberryAnnotation(self._input_type))]

    @override
    def resolver(
        self, info: Info[Any, Any], *args: Any, **kwargs: Any
    ) -> CreateOrUpdateResolverResult | Coroutine[CreateOrUpdateResolverResult, Any, Any]:
        if self.filter:
            return self._update_by_filter_resolver(info, *args, **kwargs)
        return self._update_by_ids_resolver(info, *args, **kwargs)


class StrawchemyDeleteMutationField(StrawchemyField):
    def __init__(
        self,
        input_type: type[StrawchemyTypeFromPydantic[BooleanFilterDTO[T, QueryableAttribute[Any]]]] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.is_root_field = True
        self._input_type = input_type

    def _delete_resolver(
        self,
        info: Info,
        filter_input: StrawchemyTypeFromPydantic[BooleanFilterDTO[T, QueryableAttribute[Any]]] | None = None,
    ) -> CreateOrUpdateResolverResult | Coroutine[CreateOrUpdateResolverResult, Any, Any]:
        repository = self._get_repository(info)
        return repository.delete(filter_input)

    @override
    def _validate_type(self, type_: StrawberryType | type[WithStrawberryObjectDefinition] | Any) -> None:
        # Calling self.is_list cause a recursion loop
        if not _is_list(type_):
            msg = f"Type of delete mutation must be a list: {self.name}"
            raise StrawchemyFieldError(msg)

    @override
    def auto_arguments(self) -> list[StrawberryArgument]:
        if self._input_type:
            return [
                StrawberryArgument(
                    python_name="filter_input",
                    graphql_name=FILTER_KEY,
                    default=None,
                    type_annotation=StrawberryAnnotation(self._input_type),
                )
            ]
        return []

    @override
    def resolver(
        self, info: Info[Any, Any], *args: Any, **kwargs: Any
    ) -> CreateOrUpdateResolverResult | Coroutine[CreateOrUpdateResolverResult, Any, Any]:
        return self._delete_resolver(info, *args, **kwargs)
