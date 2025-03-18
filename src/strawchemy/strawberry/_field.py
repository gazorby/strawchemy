from __future__ import annotations

import dataclasses
from functools import cached_property
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
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

from strawberry.annotation import StrawberryAnnotation
from strawberry.types import get_object_definition
from strawberry.types.arguments import StrawberryArgument
from strawberry.types.base import StrawberryList, StrawberryOptional, StrawberryType, WithStrawberryObjectDefinition
from strawberry.types.field import UNRESOLVED, StrawberryField
from strawberry.utils.inspect import in_async_context
from strawchemy.dto.base import ModelFieldT, ModelInspector, ModelT
from strawchemy.dto.types import DTOConfig, Purpose
from strawchemy.dto.utils import is_type_hint_optional
from strawchemy.graphql.constants import DISTINCT_ON_KEY, FILTER_KEY, LIMIT_KEY, NODES_KEY, OFFSET_KEY, ORDER_BY_KEY
from strawchemy.graphql.dto import BooleanFilterDTO, EnumDTO, OrderByDTO, StrawchemyDTOAttributes
from strawchemy.types import DefaultOffsetPagination

from ._utils import dto_model_from_type, strawberry_contained_type
from .exceptions import StrawchemyFieldError
from .repository import StrawchemyAsyncRepository, StrawchemySyncRepository

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine, Mapping, Sequence

    from sqlalchemy import Select
    from strawberry import BasePermission, Info
    from strawberry.experimental.pydantic.conversion_types import StrawberryTypeFromPydantic
    from strawberry.extensions.field_extension import FieldExtension
    from strawberry.types.base import StrawberryObjectDefinition, StrawberryType, WithStrawberryObjectDefinition
    from strawberry.types.fields.resolver import StrawberryResolver
    from strawchemy.graphql.dto import BooleanFilterDTO, EnumDTO, OrderByDTO
    from strawchemy.sqlalchemy.typing import QueryHookCallable
    from strawchemy.typing import AnyRepository

    from .typing import AnySessionGetter, FilterStatementCallable, StrawchemyTypeWithStrawberryObjectDefinition


__all__ = ("StrawchemyField",)

T = TypeVar("T")

ListResolverResult: TypeAlias = (
    "Sequence[StrawchemyTypeWithStrawberryObjectDefinition] | StrawchemyTypeWithStrawberryObjectDefinition"
)
GetByIdResolverResult: TypeAlias = "StrawchemyTypeWithStrawberryObjectDefinition | None"

_OPTIONAL_UNION_ARG_SIZE: int = 2


class StrawchemyField(StrawberryField, Generic[ModelT, ModelFieldT]):
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
        inspector: ModelInspector[ModelT, ModelFieldT],
        session_getter: AnySessionGetter,
        repository_type: AnyRepository,
        filter_type: type[StrawberryTypeFromPydantic[BooleanFilterDTO[T, ModelFieldT]]] | None = None,
        order_by: type[StrawberryTypeFromPydantic[OrderByDTO[T, ModelFieldT]]] | None = None,
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
        self.root_field = root_field
        self.inspector = inspector
        self.auto_snake_case = auto_snake_case
        self.root_aggregations = root_aggregations
        self.filter = filter_type
        self.order_by = order_by
        self.distinct_on = distinct_on
        self.query_hook = query_hook
        self.pagination: DefaultOffsetPagination | Literal[False] = (
            DefaultOffsetPagination() if pagination is True else pagination
        )
        self.id_field_name = id_field_name

        self._description = description
        self._session_getter = session_getter
        self._filter_statement = filter_statement
        self._execution_options = execution_options

        if repository_type == "auto":
            self._repository_type = StrawchemyAsyncRepository if in_async_context() else StrawchemySyncRepository
        else:
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

    def _auto_arguments(self) -> list[StrawberryArgument]:
        arguments: list[StrawberryArgument] = []

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
        else:
            id_fields = list(self.inspector.id_field_definitions(self._model, DTOConfig(Purpose.READ)))
            if len(id_fields) == 1:
                field = id_fields[0][1]
                arguments.append(
                    StrawberryArgument(self.id_field_name, None, type_annotation=StrawberryAnnotation(field.type_))
                )
            else:
                arguments.extend(
                    [
                        StrawberryArgument(name, None, type_annotation=StrawberryAnnotation(field.type_))
                        for name, field in self.inspector.id_field_definitions(self._model, DTOConfig(Purpose.READ))
                    ]
                )
        return arguments

    def _get_by_id_resolver(
        self, info: Info, **kwargs: Any
    ) -> GetByIdResolverResult | Coroutine[GetByIdResolverResult, Any, Any]:
        repository = self._get_repository(info)
        return repository.get_by_id(strict=not self.is_optional, **kwargs)

    def _list_resolver(
        self,
        info: Info,
        filter_input: StrawberryTypeFromPydantic[BooleanFilterDTO[T, ModelFieldT]] | None = None,
        order_by: list[StrawberryTypeFromPydantic[OrderByDTO[T, ModelFieldT]]] | None = None,
        distinct_on: list[EnumDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> ListResolverResult | Coroutine[ListResolverResult, Any, Any]:
        repository = self._get_repository(info)
        return repository.list(filter_input, order_by, distinct_on, limit, offset)

    def _check_root_aggregations(self, type_: StrawberryType | type[WithStrawberryObjectDefinition] | Any) -> None:
        inner_type = strawberry_contained_type(type_)
        if (
            self.root_aggregations
            and issubclass(inner_type, StrawchemyDTOAttributes)
            and not inner_type.__strawchemy_is_root_aggregation_type__
        ):
            msg = f"The `{self.name}` field is defined with `root_aggregations` enabled but the field type is not a root aggregation type."
            raise StrawchemyFieldError(msg)

    @cached_property
    def _model(self) -> type[ModelT]:
        return dto_model_from_type(strawberry_contained_type(self.type))

    @property
    @override
    def is_basic_field(self) -> bool:
        return not self.root_field

    @cached_property
    @override
    def is_async(self) -> bool:
        if self.base_resolver is None:
            return issubclass(self._repository_type, StrawchemyAsyncRepository)
        return super().is_async

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
            filter_type=self.filter,
            order_by=self.order_by,
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
    def description(self) -> str:
        if self._description is not None:
            return self._description
        template = "Fetch {object} from the {name} collection"
        if definition := get_object_definition(strawberry_contained_type(self.type), strict=False):
            if not self.is_list:
                description = template.format(object="object", name=definition.name)
                return f"{description} by id" if not self.base_resolver else description
            if self.root_aggregations:
                nodes_field = next(field for field in definition.fields if field.python_name == NODES_KEY)
                definition = get_object_definition(strawberry_contained_type(nodes_field.type), strict=True)
                return template.format(object="aggregation data", name=definition.name)
            return template.format(object="objects", name=definition.name)
        return template.format(object="objects", name="")

    @description.setter
    def description(self, value: str) -> None:  # pyright: ignore[reportIncompatibleVariableOverride]
        self._description = value

    @property
    @override
    def arguments(self) -> list[StrawberryArgument]:
        if self.base_resolver:
            return super().arguments
        if not self._arguments:
            self._arguments = self._auto_arguments()
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
        self._check_root_aggregations(type_)
        return type_

    def filter_statement(self, info: Info[Any, Any]) -> Select[tuple[ModelT]] | None:
        if self._filter_statement:
            return self._filter_statement(info)
        return None

    @cached_property
    def is_list(self) -> bool:
        if self.root_aggregations:
            return True
        type_ = self._type_or_annotation()
        if isinstance(type_, StrawberryOptional):
            type_ = type_.of_type
        if origin := get_origin(type_):
            type_ = origin
            if origin is Optional:
                type_ = get_args(type_)[0]
            if origin in (Union, UnionType) and len(args := get_args(type_)) == _OPTIONAL_UNION_ARG_SIZE:
                type_ = args[0] if args[0] is not type(None) else args[1]

        return isinstance(type_, StrawberryList) or type_ is list

    @cached_property
    def is_optional(self) -> bool:
        type_ = self._type_or_annotation()
        return isinstance(type_, StrawberryOptional) or is_type_hint_optional(type_)

    def resolver(
        self, info: Info[Any, Any], *args: Any, **kwargs: Any
    ) -> (
        ListResolverResult
        | Coroutine[ListResolverResult, Any, Any]
        | GetByIdResolverResult
        | Coroutine[GetByIdResolverResult, Any, Any]
    ):
        if self.is_list:
            return self._list_resolver(info, *args, **kwargs)
        return self._get_by_id_resolver(info, *args, **kwargs)

    @override
    def get_result(
        self, source: Any, info: Info[Any, Any] | None, args: list[Any], kwargs: dict[str, Any]
    ) -> Awaitable[Any] | Any:
        if self.root_field and self.base_resolver is None:
            assert info
            return self.resolver(info, *args, **kwargs)
        return super().get_result(source, info, args, kwargs)
