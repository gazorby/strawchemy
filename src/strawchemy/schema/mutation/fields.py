from __future__ import annotations

from collections.abc import Awaitable, Coroutine, Sequence
from typing import TYPE_CHECKING, Any, Optional, TypeVar

from strawberry.annotation import StrawberryAnnotation
from strawberry.types.arguments import StrawberryArgument
from typing_extensions import override

from strawchemy.constants import DATA_KEY, FILTER_KEY, UPSERT_CONFLICT_FIELDS, UPSERT_UPDATE_FIELDS
from strawchemy.exceptions import StrawchemyFieldError
from strawchemy.schema.field import StrawchemyField
from strawchemy.schema.mutation.input import Input
from strawchemy.utils.strawberry import is_list
from strawchemy.validation import InputValidationError

if TYPE_CHECKING:
    from sqlalchemy.orm import DeclarativeBase
    from strawberry import Info
    from strawberry.types.base import StrawberryType, WithStrawberryObjectDefinition

    from strawchemy.dto.strawberry import BooleanFilterDTO, EnumDTO
    from strawchemy.repository.strawberry.base import GraphQLResult
    from strawchemy.typing import AnyMappedDTO, CreateOrUpdateResolverResult, ListResolverResult, MappedGraphQLDTO
    from strawchemy.validation import ValidationProtocol


__all__ = (
    "StrawchemyCreateMutationField",
    "StrawchemyDeleteMutationField",
    "StrawchemyUpdateMutationField",
    "StrawchemyUpsertMutationField",
)

T = TypeVar("T", bound="DeclarativeBase")


class _StrawchemyInputMutationField(StrawchemyField):
    def __init__(
        self,
        input_type: type[MappedGraphQLDTO[T]],
        *args: Any,
        validation: ValidationProtocol[T] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.is_root_field = True
        self._input_type = input_type
        self._validation = validation


class _StrawchemyMutationField:
    async def _input_result_async(
        self, repository_call: Awaitable[GraphQLResult[Any, Any]], input_data: Input[Any]
    ) -> ListResolverResult:
        result = await repository_call
        return result.graphql_list() if input_data.list_input else result.graphql_type()

    def _input_result_sync(
        self, repository_call: GraphQLResult[Any, Any], input_data: Input[Any]
    ) -> ListResolverResult:
        return repository_call.graphql_list() if input_data.list_input else repository_call.graphql_type()


class StrawchemyCreateMutationField(_StrawchemyInputMutationField, _StrawchemyMutationField):
    def _create_resolver(
        self, info: Info, data: AnyMappedDTO | Sequence[AnyMappedDTO]
    ) -> CreateOrUpdateResolverResult | Coroutine[CreateOrUpdateResolverResult, Any, Any]:
        repository = self._get_repository(info)
        try:
            input_data = Input(data, self._validation)
        except InputValidationError as error:
            return error.graphql_type()
        if self._is_repo_async(repository):
            return self._input_result_async(repository.create(input_data), input_data)
        return self._input_result_sync(repository.create(input_data), input_data)

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


class StrawchemyUpsertMutationField(_StrawchemyInputMutationField, _StrawchemyMutationField):
    def __init__(
        self,
        input_type: type[MappedGraphQLDTO[T]],
        update_fields_enum: type[EnumDTO],
        conflict_fields_enum: type[EnumDTO],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(input_type, *args, **kwargs)
        self._update_fields_enum = update_fields_enum
        self._conflict_fields_enum = conflict_fields_enum

    def _upsert_resolver(
        self,
        info: Info,
        data: AnyMappedDTO | Sequence[AnyMappedDTO],
        filter_input: BooleanFilterDTO | None = None,
        update_fields: list[EnumDTO] | None = None,
        conflict_fields: EnumDTO | None = None,
    ) -> CreateOrUpdateResolverResult | Coroutine[CreateOrUpdateResolverResult, Any, Any]:
        repository = self._get_repository(info)
        try:
            input_data = Input(data, self._validation)
        except InputValidationError as error:
            return error.graphql_type()
        if self._is_repo_async(repository):
            return self._input_result_async(
                repository.upsert(input_data, filter_input, update_fields, conflict_fields), input_data
            )
        return self._input_result_sync(
            repository.upsert(input_data, filter_input, update_fields, conflict_fields), input_data
        )

    @override
    def auto_arguments(self) -> list[StrawberryArgument]:
        arguments = [
            StrawberryArgument(
                UPSERT_UPDATE_FIELDS,
                None,
                type_annotation=StrawberryAnnotation(Optional[list[self._update_fields_enum]]),
                default=None,
            ),
            StrawberryArgument(
                UPSERT_CONFLICT_FIELDS,
                None,
                type_annotation=StrawberryAnnotation(Optional[self._conflict_fields_enum]),
                default=None,
            ),
        ]
        if self.is_list:
            arguments.append(
                StrawberryArgument(DATA_KEY, None, type_annotation=StrawberryAnnotation(list[self._input_type]))
            )
        else:
            arguments.append(StrawberryArgument(DATA_KEY, None, type_annotation=StrawberryAnnotation(self._input_type)))
        return arguments

    @override
    def resolver(
        self, info: Info[Any, Any], *args: Any, **kwargs: Any
    ) -> CreateOrUpdateResolverResult | Coroutine[CreateOrUpdateResolverResult, Any, Any]:
        return self._upsert_resolver(info, *args, **kwargs)


class StrawchemyUpdateMutationField(_StrawchemyInputMutationField, _StrawchemyMutationField):
    @override
    def _validate_type(self, type_: StrawberryType | type[WithStrawberryObjectDefinition] | Any) -> None:
        if self._filter is not None and not is_list(type_):
            msg = f"Type of update mutation by filter must be a list: {self.name}"
            raise StrawchemyFieldError(msg)

    def _update_by_ids_resolver(
        self, info: Info, data: AnyMappedDTO | Sequence[AnyMappedDTO], **_: Any
    ) -> CreateOrUpdateResolverResult | Coroutine[CreateOrUpdateResolverResult, Any, Any]:
        repository = self._get_repository(info)
        try:
            input_data = Input(data, self._validation)
        except InputValidationError as error:
            error_result = error.graphql_type()
            return [error_result] if isinstance(data, Sequence) else error_result

        if self._is_repo_async(repository):
            return self._input_result_async(repository.update_by_id(input_data), input_data)
        return self._input_result_sync(repository.update_by_id(input_data), input_data)

    def _update_by_filter_resolver(
        self, info: Info, data: AnyMappedDTO, filter_input: BooleanFilterDTO
    ) -> CreateOrUpdateResolverResult | Coroutine[CreateOrUpdateResolverResult, Any, Any]:
        repository = self._get_repository(info)
        try:
            input_data = Input(data, self._validation)
        except InputValidationError as error:
            return [error.graphql_type()]
        if self._is_repo_async(repository):
            return self._list_result_async(repository.update_by_filter(input_data, filter_input))
        return self._list_result_sync(repository.update_by_filter(input_data, filter_input))

    @override
    def auto_arguments(self) -> list[StrawberryArgument]:
        if self.filter:
            return [
                StrawberryArgument(DATA_KEY, None, type_annotation=StrawberryAnnotation(self._input_type)),
                StrawberryArgument(
                    python_name="filter_input",
                    graphql_name=FILTER_KEY,
                    type_annotation=StrawberryAnnotation(Optional[self.filter]),
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
        if self._filter is None:
            return self._update_by_ids_resolver(info, *args, **kwargs)
        return self._update_by_filter_resolver(info, *args, **kwargs)


class StrawchemyDeleteMutationField(StrawchemyField, _StrawchemyMutationField):
    def __init__(
        self,
        input_type: type[BooleanFilterDTO] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.is_root_field = True
        self._input_type = input_type

    def _delete_resolver(
        self,
        info: Info,
        filter_input: BooleanFilterDTO | None = None,
    ) -> CreateOrUpdateResolverResult | Coroutine[CreateOrUpdateResolverResult, Any, Any]:
        repository = self._get_repository(info)
        if self._is_repo_async(repository):
            return self._list_result_async(repository.delete(filter_input))
        return self._list_result_sync(repository.delete(filter_input))

    @override
    def _validate_type(self, type_: StrawberryType | type[WithStrawberryObjectDefinition] | Any) -> None:
        # Calling self.is_list cause a recursion loop
        if not is_list(type_):
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
