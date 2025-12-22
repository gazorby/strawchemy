from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Generic, Protocol, get_args, get_origin

from strawchemy.dto import DTOConfig, DTOFieldDefinition, ModelFieldT, ModelT
from strawchemy.utils.annotation import non_optional_type_hint

if TYPE_CHECKING:
    from collections.abc import Iterable

    from strawchemy.dto.base import Relation
    from strawchemy.utils.graph import Node


class ModelInspector(Protocol, Generic[ModelT, ModelFieldT]):
    def field_definitions(
        self, model: type[Any], dto_config: DTOConfig
    ) -> Iterable[tuple[str, DTOFieldDefinition[ModelT, ModelFieldT]]]: ...

    def id_field_definitions(
        self, model: type[Any], dto_config: DTOConfig
    ) -> list[tuple[str, DTOFieldDefinition[ModelT, ModelFieldT]]]: ...

    def field_definition(
        self, model_field: ModelFieldT, dto_config: DTOConfig
    ) -> DTOFieldDefinition[ModelT, ModelFieldT]: ...

    def get_type_hints(self, type_: type[Any], include_extras: bool = True) -> dict[str, Any]: ...

    def relation_model(self, model_field: ModelFieldT) -> type[Any]: ...

    def model_field_type(self, field_definition: DTOFieldDefinition[ModelT, ModelFieldT]) -> Any:
        type_hint = (
            field_definition.type_hint_override if field_definition.has_type_override else field_definition.type_hint
        )
        if get_origin(type_hint) is Annotated:
            return get_args(type_hint)[0]
        return non_optional_type_hint(type_hint)

    def relation_cycle(
        self, field: DTOFieldDefinition[Any, ModelFieldT], node: Node[Relation[ModelT, Any], None]
    ) -> bool: ...

    def has_default(self, model_field: ModelFieldT) -> bool: ...

    def required(self, model_field: ModelFieldT) -> bool: ...

    def is_foreign_key(self, model_field: ModelFieldT) -> bool: ...

    def is_primary_key(self, model_field: ModelFieldT) -> bool: ...

    def reverse_relation_required(self, model_field: ModelFieldT) -> bool: ...
