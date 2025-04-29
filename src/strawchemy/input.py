from __future__ import annotations

import dataclasses
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, Literal, Self, TypeAlias, TypeVar, cast, override

from pydantic import ValidationError

from sqlalchemy import event, inspect
from sqlalchemy.orm import NO_VALUE, MapperProperty, RelationshipDirection, object_mapper
from strawchemy.dto.base import DTOFieldDefinition, MappedDTO, ToMappedProtocol, VisitorProtocol
from strawchemy.graphql.mutation import (
    RelationType,
    RequiredToManyUpdateInputMixin,
    RequiredToOneInputMixin,
    ToManyCreateInputMixin,
    ToManyUpdateInputMixin,
    ToOneInputMixin,
)

from .exceptions import InputValidationError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
    from strawchemy.dto.backend.pydantic import MappedPydanticDTO


__all__ = (
    "Input",
    "LevelInput",
    "RelationType",
    "RequiredToManyUpdateInputMixin",
    "RequiredToOneInputMixin",
    "ToManyCreateInputMixin",
    "ToManyUpdateInputMixin",
    "ToOneInputMixin",
)

T = TypeVar("T", bound=MappedDTO[Any])
DeclarativeBaseT = TypeVar("DeclarativeBaseT", bound="DeclarativeBase")
InputModel = TypeVar("InputModel", bound="DeclarativeBase")
RelationInputT = TypeVar("RelationInputT", bound=MappedDTO[Any])
RelationInputType: TypeAlias = Literal["set", "create", "add", "remove"]


def _has_record(model: DeclarativeBase) -> bool:
    state = inspect(model)
    return state.persistent or state.detached


@dataclass
class _UnboundRelationInput:
    attribute: MapperProperty[Any]
    related: type[DeclarativeBase]
    relation_type: RelationType
    set: list[DeclarativeBase] | None = dataclasses.field(default_factory=list)
    add: list[DeclarativeBase] = dataclasses.field(default_factory=list)
    remove: list[DeclarativeBase] = dataclasses.field(default_factory=list)
    create: list[DeclarativeBase] = dataclasses.field(default_factory=list)
    input_index: int = -1
    level: int = 0

    def add_instance(self, model: DeclarativeBase) -> None:
        if not _has_record(model):
            self.create.append(model)
        elif self.relation_type is RelationType.TO_ONE:
            if self.set:
                self.set.append(model)
            else:
                self.set = [model]
        else:
            self.add.append(model)

    def __bool__(self) -> bool:
        return bool(self.set or self.add or self.remove or self.create) or self.set is None


@dataclass(kw_only=True)
class RelationInput(_UnboundRelationInput):
    parent: DeclarativeBase

    def __post_init__(self) -> None:
        if self.relation_type is RelationType.TO_ONE:
            event.listens_for(self.attribute, "set")(self._set_event)
        else:
            event.listens_for(self.attribute, "append")(self._append_event)
            event.listens_for(self.attribute, "remove")(self._remove_event)

    @classmethod
    def from_unbound(cls, unbound: _UnboundRelationInput, model: DeclarativeBase) -> Self:
        return cls(
            attribute=unbound.attribute,
            related=unbound.related,
            parent=model,
            set=unbound.set,
            add=unbound.add,
            remove=unbound.remove,
            relation_type=unbound.relation_type,
            create=unbound.create,
            input_index=unbound.input_index,
            level=unbound.level,
        )

    def _set_event(self, target: DeclarativeBase, value: DeclarativeBase | None, *_: Any, **__: Any) -> None:
        if value is None:
            return
        if _has_record(value):
            self.set = [value]
        else:
            self.create = [value]

    def _append_event(self, target: DeclarativeBase, value: DeclarativeBase, *_: Any, **__: Any) -> None:
        if _has_record(value):
            self.add.append(value)
        else:
            self.create.append(value)

    def _remove_event(self, target: DeclarativeBase, value: DeclarativeBase, *_: Any, **__: Any) -> None:
        if _has_record(value):
            self.add = [model for model in self.add if model is not value]
        else:
            self.create = [model for model in self.create if model is not value]


@dataclass
class _InputVisitor(VisitorProtocol, Generic[InputModel]):
    input_data: Input[InputModel]

    current_relations: list[_UnboundRelationInput] = dataclasses.field(default_factory=list)

    @override
    def field_value(
        self,
        parent: ToMappedProtocol,
        field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        value: Any,
        level: int,
    ) -> Any:
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
            assert field.related_model
            self.current_relations.append(
                _UnboundRelationInput(
                    attribute=field.model_field.property,
                    related=field.related_model,
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
    def model(
        self,
        parent: ToMappedProtocol,
        model_cls: type[DeclarativeBase],
        params: dict[str, Any],
        override: dict[str, Any],
        level: int,
    ) -> Any:
        if level == 1 and self.input_data.pydantic_model is not None:
            try:
                model = self.input_data.pydantic_model.model_validate(params).to_mapped(override=override)
            except ValidationError as error:
                raise InputValidationError(error) from error
        else:
            model = model_cls(**params)
        for relation in self.current_relations:
            self.input_data.add_relation(RelationInput.from_unbound(relation, model))
        self.current_relations.clear()
        # Return dict because .model_validate will be called at root level
        if level != 1 and self.input_data.pydantic_model is not None:
            return params
        return model


@dataclass
class _FilteredRelationInput:
    relation: RelationInput
    instance: DeclarativeBase


@dataclass
class LevelInput:
    inputs: list[_FilteredRelationInput] = field(default_factory=list)


class Input(Generic[InputModel]):
    def __init__(
        self,
        dtos: MappedDTO[InputModel] | Sequence[MappedDTO[InputModel]],
        validation: type[MappedPydanticDTO[InputModel]] | None = None,
        **override: Any,
    ) -> None:
        self.max_level = 0
        self.relations: list[RelationInput] = []
        self.instances: list[InputModel] = []
        self.dtos: list[MappedDTO[InputModel]] = []
        self.pydantic_model = validation

        dtos = dtos if isinstance(dtos, Sequence) else [dtos]
        for index, dto in enumerate(dtos):
            mapped = dto.to_mapped(visitor=_InputVisitor(self), override=override)
            self.instances.append(mapped)
            self.dtos.append(dto)
            for relation in self.relations:
                if relation.input_index == -1:
                    relation.input_index = index

    @classmethod
    def _model_identity(cls, model: DeclarativeBase) -> Hashable:
        return inspect(model)

    def _add_non_input_relations(
        self, model: DeclarativeBase, input_index: int, _level: int = 0, _seen: set[Hashable] | None = None
    ) -> None:
        seen = _seen or set()
        _level += 1
        loaded_attributes = {name for name, attr in inspect(model).attrs.items() if attr.loaded_value is not NO_VALUE}
        level_relations = {relation.attribute.key for relation in self.relations if relation.level == _level}
        mapper = object_mapper(model)
        seen.add(self._model_identity(model))
        for relationship in mapper.relationships:
            if relationship.key not in loaded_attributes or relationship.key in level_relations:
                continue
            relationship_value = getattr(model, relationship.key)
            # We do not merge this check with the one above to avoid MissingGreenlet error
            # If the attribute is not loaded when using asyncio, it won't appears in loaded_attributes
            if relationship_value is None:
                continue
            relation_type = (
                RelationType.TO_MANY
                if relationship.direction in {RelationshipDirection.MANYTOMANY, RelationshipDirection.ONETOMANY}
                else RelationType.TO_ONE
            )
            relation = RelationInput(
                attribute=relationship,
                parent=model,
                level=_level,
                input_index=input_index,
                relation_type=relation_type,
                related=relationship.entity.mapper.class_,
            )
            if isinstance(relationship_value, tuple | list):
                model_list = cast("list[DeclarativeBase]", relationship_value)
                for value in model_list:
                    if self._model_identity(value) in seen:
                        continue
                    self._add_non_input_relations(value, input_index, _level, seen)
                    relation.add_instance(value)
            elif self._model_identity(relationship_value) not in seen:
                self._add_non_input_relations(relationship_value, input_index, _level, seen)
                relation.add_instance(relationship_value)
            self.add_relation(relation)

    def add_relation(self, relation: RelationInput) -> None:
        if relation:
            self.relations.append(relation)
            self.max_level = max(self.max_level, relation.level)

    def filter_by_level(
        self, relation_type: RelationType, input_types: Iterable[RelationInputType]
    ) -> list[LevelInput]:
        levels: list[LevelInput] = []
        level_range = (
            range(1, self.max_level + 1) if relation_type is RelationType.TO_MANY else range(self.max_level, 0, -1)
        )
        for level in level_range:
            level_input = LevelInput()
            for relation in self.relations:
                input_data: list[_FilteredRelationInput] = []
                for input_type in input_types:
                    relation_input = getattr(relation, input_type)
                    if not relation_input or relation.level != level:
                        continue
                    input_data.extend(
                        _FilteredRelationInput(relation, mapped)
                        for mapped in relation_input
                        if relation.relation_type is relation_type
                    )
                    level_input.inputs.extend(input_data)
            if level_input.inputs:
                levels.append(level_input)

        return levels

    def add_non_input_relations(self) -> None:
        for i, instance in enumerate(self.instances):
            self._add_non_input_relations(instance, i)
