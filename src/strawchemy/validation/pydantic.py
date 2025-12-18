from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import ValidationError
from sqlalchemy.orm import DeclarativeBase
from typing_extensions import override

from strawchemy.dto.backend.pydantic import MappedPydanticDTO, PydanticDTOBackend
from strawchemy.dto.base import ModelT
from strawchemy.dto.utils import read_partial
from strawchemy.strawberry.dto import StrawchemyDTOAttributes
from strawchemy.strawberry.factories.types import InputFactory
from strawchemy.strawberry.mutation.types import LocalizedErrorType, ValidationErrorType
from strawchemy.utils import snake_to_lower_camel_case
from strawchemy.validation.base import InputValidationError, T, ValidationProtocol

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from pydantic_core import ErrorDetails
    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute

    from strawchemy import Strawchemy
    from strawchemy.dto.base import DTOFieldDefinition, MappedDTO, Relation
    from strawchemy.dto.types import DTOConfig, ExcludeFields, IncludeFields, Purpose
    from strawchemy.graph import Node
    from strawchemy.sqlalchemy.typing import DeclarativeT
    from strawchemy.strawberry.typing import GraphQLPurpose


@dataclass
class PydanticValidation(ValidationProtocol[T]):
    model: type[MappedPydanticDTO[T]]
    to_camel: bool = True

    @classmethod
    def _to_localized_error(cls, errors: ErrorDetails, to_camel: bool) -> LocalizedErrorType:
        return LocalizedErrorType(
            loc=[snake_to_lower_camel_case(str(loc)) if to_camel else str(loc) for loc in errors["loc"]],
            message=errors["msg"],
            type=errors["type"],
        )

    @override
    def validate(self, **kwargs: Any) -> MappedDTO[T]:
        try:
            return self.model.model_validate(kwargs)
        except ValidationError as error:
            raise InputValidationError(self, error) from error

    @override
    def to_error(self, exception: ValidationError) -> ValidationErrorType:
        return ValidationErrorType(errors=[self._to_localized_error(err, self.to_camel) for err in exception.errors()])


class MappedPydanticGraphQLDTO(StrawchemyDTOAttributes, MappedPydanticDTO[ModelT]):
    __strawchemy_filter__: ClassVar[type[Any] | None] = None
    __strawchemy_order_by__: ClassVar[type[Any] | None] = None


class StrawchemyInputValidationFactory(InputFactory[MappedPydanticGraphQLDTO[Any]]):
    @override
    def _resolve_type(
        self,
        field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        dto_config: DTOConfig,
        node: Node[Relation[DeclarativeBase, MappedPydanticGraphQLDTO[Any]], None],
        *,
        mode: GraphQLPurpose,
        **factory_kwargs: Any,
    ) -> Any:
        if not field.is_relation:
            return self._resolve_basic_type(field, dto_config)
        return self._resolve_relation_type(field, dto_config, node, mode=mode, **factory_kwargs)

    if TYPE_CHECKING:

        @override
        def input(
            self,
            model: type[DeclarativeT],
            *,
            mode: GraphQLPurpose,
            include: IncludeFields | None = None,
            exclude: ExcludeFields | None = None,
            partial: bool | None = None,
            type_map: Mapping[Any, Any] | None = None,
            aliases: Mapping[str, str] | None = None,
            alias_generator: Callable[[str], str] | None = None,
            name: str | None = None,
            description: str | None = None,
            directives: Sequence[object] | None = (),
            override: bool = False,
            purpose: Purpose = Purpose.WRITE,
            **kwargs: Any,
        ) -> Callable[[type[Any]], type[MappedPydanticGraphQLDTO[DeclarativeT]]]: ...

    @override
    def factory(
        self,
        model: type[DeclarativeT],
        dto_config: DTOConfig = read_partial,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        current_node: Node[Relation[Any, MappedPydanticGraphQLDTO[T]], None] | None = None,
        raise_if_no_fields: bool = False,
        tags: set[str] | None = None,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        description: str | None = None,
        mode: GraphQLPurpose,
        **kwargs: Any,
    ) -> type[MappedPydanticGraphQLDTO[DeclarativeT]]:
        return super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            tags,
            backend_kwargs=backend_kwargs,
            description=description or f"{mode.capitalize()} validation type",
            mode=mode,
            register_type=False,
            **kwargs,
        )


class PydanticMapper:
    """Provides methods to generate Pydantic models for input validation.

    This class leverages a `StrawchemyInputValidationFactory` to create
    Pydantic models tailored for different input scenarios such as creation,
    update by primary key, and update by filter.
    """

    def __init__(self, strawchemy: Strawchemy) -> None:
        """Initializes the PydanticMapper.

        Args:
            strawchemy: An instance of the Strawchemy class.
        """
        pydantic_backend = PydanticDTOBackend(MappedPydanticGraphQLDTO)
        self._strawchemy: Strawchemy = strawchemy
        """The Strawchemy instance used for schema introspection."""
        self._validation_factory: StrawchemyInputValidationFactory = StrawchemyInputValidationFactory(
            self._strawchemy, pydantic_backend
        )
        """Factory for creating input validation Pydantic models."""

        self.create = partial(self._validation_factory.input, mode="create_input")
        """Generates a Pydantic model for 'create' input validation."""
        self.pk_update = partial(self._validation_factory.input, mode="update_by_pk_input")
        """Generates a Pydantic model for 'update_by_pk' input validation."""
        self.filter_update = partial(self._validation_factory.input, mode="update_by_filter_input")
        """Generates a Pydantic model for 'update_by_filter' input validation."""
