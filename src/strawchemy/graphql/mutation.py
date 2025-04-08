from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Generic, Literal, Self, TypeVar, override

from strawchemy.dto.base import DTOFieldDefinition, MappedDTO, ModelFieldT, ModelT, ToMappedProtocol, VisitorProtocol
from strawchemy.dto.types import DTO_UNSET, DTOUnsetType

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from strawchemy.graphql.typing import AnyMappedDTO

T = TypeVar("T", bound=MappedDTO[Any])
RelationInputT = TypeVar("RelationInputT", bound=MappedDTO[Any])


class RelationType(Enum):
    TO_ONE = auto()
    TO_MANY = auto()


class ToOneInputMixin(ToMappedProtocol, Generic[T, RelationInputT]):
    set: T | None
    create: RelationInputT | None

    @override
    def to_mapped(
        self, visitor: VisitorProtocol | None = None, override: dict[str, Any] | None = None, level: int = 0
    ) -> Any | DTOUnsetType:
        if self.create and self.set:
            msg = "You cannot use both `set` and `create` in a -to-one relation input"
            raise ValueError(msg)
        return self.create.to_mapped(visitor, level=level) if self.create else DTO_UNSET


class RequiredToOneInputMixin(ToOneInputMixin[T, RelationInputT]):
    @override
    def to_mapped(
        self, visitor: VisitorProtocol | None = None, override: dict[str, Any] | None = None, level: int = 0
    ) -> Any | DTOUnsetType:
        if not self.create and not self.set:
            msg = "Relation is required, you must set either `set` or `create`."
            raise ValueError(msg)
        return super().to_mapped(visitor, level=level)


class ToManyCreateInputMixin(ToMappedProtocol, Generic[T, RelationInputT]):
    set: list[T] | None
    add: list[T] | None
    create: list[RelationInputT] | None

    @override
    def to_mapped(
        self, visitor: VisitorProtocol | None = None, override: dict[str, Any] | None = None, level: int = 0
    ) -> list[Any] | DTOUnsetType:
        if self.set and (self.create or self.add):
            msg = "You cannot use `set` with `create` or `add` in -to-many relation input"
            raise ValueError(msg)
        return [dto.to_mapped(visitor, level=level) for dto in self.create] if self.create else DTO_UNSET


class RequiredToManyUpdateInputMixin(ToMappedProtocol, Generic[T, RelationInputT]):
    add: list[T] | None
    create: list[RelationInputT] | None

    @override
    def to_mapped(
        self, visitor: VisitorProtocol | None = None, override: dict[str, Any] | None = None, level: int = 0
    ) -> list[Any] | DTOUnsetType:
        return [dto.to_mapped(visitor, level=level) for dto in self.create] if self.create else DTO_UNSET


class ToManyUpdateInputMixin(RequiredToManyUpdateInputMixin[T, RelationInputT]):
    set: list[T] | None
    remove: list[T] | None

    @override
    def to_mapped(
        self, visitor: VisitorProtocol | None = None, override: dict[str, Any] | None = None, level: int = 0
    ) -> list[Any] | DTOUnsetType:
        if self.set and (self.create or self.add or self.remove):
            msg = "You cannot use `set` with `create`, `add` or `remove` in a -to-many relation input"
            raise ValueError(msg)
        return super().to_mapped(visitor, level=level)


@dataclass
class _UnboundRelationInput(Generic[ModelT, ModelFieldT]):
    field: DTOFieldDefinition[ModelT, ModelFieldT]
    relation_type: RelationType
    set: list[ModelT] | None = dataclasses.field(default_factory=list)
    add: list[ModelT] = dataclasses.field(default_factory=list)
    remove: list[ModelT] = dataclasses.field(default_factory=list)
    create: list[ModelT] = dataclasses.field(default_factory=list)
    input_index: int = -1
    level: int = 0


@dataclass(kw_only=True)
class RelationInput(_UnboundRelationInput[ModelT, ModelFieldT], Generic[ModelT, ModelFieldT]):
    parent: ModelT

    @classmethod
    def from_unbound(cls, unbound: _UnboundRelationInput[ModelT, ModelFieldT], model: ModelT) -> Self:
        return cls(
            parent=model,
            field=unbound.field,
            set=unbound.set,
            add=unbound.add,
            remove=unbound.remove,
            relation_type=unbound.relation_type,
            create=unbound.create,
            input_index=unbound.input_index,
            level=unbound.level,
        )


@dataclass
class InputVisitor(VisitorProtocol, Generic[ModelT, ModelFieldT]):
    input_data: InputData[ModelT, ModelFieldT]

    current_relations: list[_UnboundRelationInput[ModelT, ModelFieldT]] = dataclasses.field(default_factory=list)

    @override
    def field_value(self, parent: ToMappedProtocol, field: DTOFieldDefinition[Any, Any], value: Any, level: int) -> Any:
        field_value = getattr(parent, field.model_field_name)
        add, remove, create = [], [], []
        set_: list[Any] | None = []
        relation_type = RelationType.TO_MANY
        if isinstance(field_value, ToOneInputMixin):
            relation_type = RelationType.TO_ONE
            if field_value.set is None:
                set_ = None
            elif field_value.set:
                set_ = [field_value.set.to_mapped()]
        elif isinstance(field_value, ToManyUpdateInputMixin | ToManyCreateInputMixin):
            if field_value.set:
                set_ = [dto.to_mapped() for dto in field_value.set]
            if field_value.add:
                add = [dto.to_mapped() for dto in field_value.add]
        if isinstance(field_value, ToManyUpdateInputMixin) and field_value.remove:
            remove = [dto.to_mapped() for dto in field_value.remove]
        if (
            isinstance(field_value, ToOneInputMixin | ToManyUpdateInputMixin | ToManyCreateInputMixin)
            and field_value.create
        ):
            create = value if isinstance(value, list) else [value]
        if set_ is None or set_ or add or remove or create:
            self.current_relations.append(
                _UnboundRelationInput(
                    field=field,
                    relation_type=relation_type,
                    set=set_,
                    add=add,
                    remove=remove,
                    create=create,
                    level=level,
                )
            )
        return value

    @override
    def model(self, model: ModelT, level: int) -> ModelT:
        for relation in self.current_relations:
            assert relation.field.related_model
            relation_input = RelationInput.from_unbound(relation, model)
            self.input_data.relations.append(relation_input)
        self.current_relations.clear()
        return model


@dataclass
class InputData(Generic[ModelT, ModelFieldT]):
    input_dtos: Sequence[AnyMappedDTO]
    input_instances: list[ModelT] = field(init=False, default_factory=list)
    relations: list[RelationInput[ModelT, ModelFieldT]] = field(default_factory=list)
    max_level: int = 0

    def __post_init__(self) -> None:
        for index, dto in enumerate(self.input_dtos):
            mapped = dto.to_mapped(visitor=InputVisitor(self))
            self.input_instances.append(mapped)
            for relation in self.relations:
                self.max_level = max(self.max_level, relation.level)
                if relation.input_index == -1:
                    relation.input_index = index

    def filter_by_level(
        self, relation_type: RelationType, input_types: Iterable[Literal["set", "create", "add", "remove"]]
    ) -> list[LevelInput[ModelT, ModelFieldT]]:
        levels: list[LevelInput[ModelT, ModelFieldT]] = []
        level_range = (
            range(1, self.max_level + 1) if relation_type is RelationType.TO_MANY else range(self.max_level, 0, -1)
        )
        for level in level_range:
            level_input = LevelInput()
            for relation in self.relations:
                input_data: list[FilteredRelationInput[ModelT, ModelFieldT]] = []
                for input_type in input_types:
                    relation_input = getattr(relation, input_type)
                    if not relation_input or relation.level != level:
                        continue
                    input_data.extend(
                        FilteredRelationInput(relation, mapped)
                        for mapped in relation_input
                        if relation.relation_type is relation_type
                    )
                    level_input.inputs.extend(input_data)
            if level_input.inputs:
                levels.append(level_input)

        return levels


@dataclass
class FilteredRelationInput(Generic[ModelT, ModelFieldT]):
    relation: RelationInput[ModelT, ModelFieldT]
    instance: ModelT


@dataclass
class LevelInput(Generic[ModelT, ModelFieldT]):
    inputs: list[FilteredRelationInput[ModelT, ModelFieldT]] = field(default_factory=list)
