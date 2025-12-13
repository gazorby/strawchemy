from __future__ import annotations

import dataclasses
from collections.abc import Hashable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeAlias, TypeVar, cast, final

from sqlalchemy.orm import MapperProperty, RelationshipDirection, object_mapper
from typing_extensions import Self, override

from sqlalchemy import event, inspect
from strawchemy.dto.base import DTOFieldDefinition, MappedDTO, ToMappedProtocol, VisitorProtocol
from strawchemy.dto.inspectors.sqlalchemy import SQLAlchemyInspector

from .types import RelationType, ToManyCreateInput, ToManyUpdateInput, ToManyUpsertInput, ToOneInput, ToOneUpsertInput

if TYPE_CHECKING:
    from collections.abc import Iterable
    from enum import Enum

    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute

    from strawchemy.strawberry.dto import EnumDTO
    from strawchemy.strawberry.typing import MappedGraphQLDTO
    from strawchemy.validation.base import ValidationProtocol


__all__ = ("Input", "LevelInput", "RelationType")

T = TypeVar("T", bound=MappedDTO[Any])
DeclarativeBaseT = TypeVar("DeclarativeBaseT", bound="DeclarativeBase")
InputModel = TypeVar("InputModel", bound="DeclarativeBase")
RelationInputT = TypeVar("RelationInputT", bound=MappedDTO[Any])
RelationInputType: TypeAlias = Literal["set", "create", "add", "remove", "upsert"]


@final
class _Unset: ...


def _has_record(model: DeclarativeBase) -> bool:
    state = inspect(model)
    return state.persistent or state.detached


@dataclass(frozen=True)
class UpsertData:
    instances: list[DeclarativeBase] = dataclasses.field(default_factory=list)
    conflict_constraint: Enum | None = None
    update_fields: list[EnumDTO] = dataclasses.field(default_factory=list)

    @classmethod
    def from_upsert_input(cls, data: ToOneUpsertInput[Any, Any, Any] | ToManyUpsertInput[Any, Any, Any]) -> Self:
        instances = data.to_mapped()
        return cls(
            instances=instances if isinstance(instances, list) else [instances],
            update_fields=data.update_fields or [],
            conflict_constraint=data.conflict_fields,
        )

    def __iter__(self) -> Iterator[DeclarativeBase]:
        return iter(self.instances)


class _UnboundRelationInput:
    def __init__(
        self,
        attribute: MapperProperty[Any],
        related: type[DeclarativeBase],
        relation_type: RelationType,
        set_: list[DeclarativeBase] | None | type[_Unset] = _Unset,
        add: list[DeclarativeBase] | None = None,
        remove: list[DeclarativeBase] | None = None,
        create: list[DeclarativeBase] | None = None,
        upsert: UpsertData | None = None,
        input_index: int = -1,
        level: int = 0,
    ) -> None:
        self.attribute = attribute
        self.related = related
        self.relation_type = relation_type
        self.set: list[DeclarativeBase] | None = set_ if set_ is not _Unset else []
        self.add = add if add is not None else []
        self.remove = remove if remove is not None else []
        self.create = create if create is not None else []
        self.upsert = upsert
        self.input_index = input_index
        self.level = level

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
        return bool(self.set or self.add or self.remove or self.create or self.upsert) or self.set is None


class RelationInput(_UnboundRelationInput):
    def __init__(
        self,
        attribute: MapperProperty[Any],
        related: type[DeclarativeBase],
        parent: DeclarativeBase,
        relation_type: RelationType,
        set_: list[DeclarativeBase] | None | type[_Unset] = _Unset,
        add: list[DeclarativeBase] | None = None,
        remove: list[DeclarativeBase] | None = None,
        create: list[DeclarativeBase] | None = None,
        upsert: UpsertData | None = None,
        input_index: int = -1,
        level: int = 0,
    ) -> None:
        super().__init__(
            attribute=attribute,
            related=related,
            relation_type=relation_type,
            set_=set_,
            add=add,
            remove=remove,
            create=create,
            upsert=upsert,
            input_index=input_index,
            level=level,
        )
        self.parent = parent

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
            set_=unbound.set,
            add=unbound.add,
            remove=unbound.remove,
            relation_type=unbound.relation_type,
            create=unbound.create,
            input_index=unbound.input_index,
            level=unbound.level,
            upsert=unbound.upsert,
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
class _InputVisitor(VisitorProtocol[DeclarativeBaseT], Generic[DeclarativeBaseT, InputModel]):
    input_data: Input[InputModel]
    is_update: bool = False

    current_relations: list[_UnboundRelationInput] = dataclasses.field(default_factory=list)

    @override
    def field_value(
        self,
        parent: ToMappedProtocol[DeclarativeBaseT],
        field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        value: Any,
        level: int,
    ) -> Any:
        field_value = getattr(parent, field.model_field_name)
        add, remove, create = [], [], []
        set_: list[Any] | None = []
        upsert: UpsertData | None = None
        relation_type = RelationType.TO_MANY
        if isinstance(field_value, ToOneInput):
            relation_type = RelationType.TO_ONE
            if field_value.set is None:
                set_ = None
            elif field_value.set:
                set_ = [field_value.set.to_mapped()]
        elif isinstance(field_value, (ToManyUpdateInput, ToManyCreateInput)):
            if field_value.set:
                set_ = [dto.to_mapped() for dto in field_value.set]
            if field_value.add:
                add = [dto.to_mapped() for dto in field_value.add]
        if isinstance(field_value, ToManyUpdateInput) and field_value.remove:
            remove = [dto.to_mapped() for dto in field_value.remove]
        if isinstance(field_value, (ToOneInput, ToManyUpdateInput, ToManyCreateInput)):
            if field_value.create:
                create = value if isinstance(value, list) else [value]
            if field_value.upsert:
                upsert = UpsertData.from_upsert_input(field_value.upsert)
        if set_ is None or set_ or add or remove or create or upsert is not None:
            assert field.related_model
            self.current_relations.append(
                _UnboundRelationInput(
                    attribute=field.model_field.property,
                    related=field.related_model,
                    relation_type=relation_type,
                    set_=set_,
                    add=add,
                    remove=remove,
                    create=create,
                    level=level,
                    upsert=upsert,
                )
            )
        return value

    @override
    def model(
        self,
        parent: ToMappedProtocol[DeclarativeBaseT],
        model_cls: type[DeclarativeBaseT],
        params: dict[str, Any],
        override: dict[str, Any],
        level: int,
    ) -> Any:
        if level == 1 and self.input_data.validation is not None:
            model = self.input_data.validation.validate(**params).to_mapped(override=override)
        else:
            model = model_cls(**params)

        # In update mode, we ensure only input params are set in the instance
        if self.is_update:
            for attribute in SQLAlchemyInspector.loaded_attributes(model):
                if attribute not in params:
                    delattr(model, attribute)

        for relation in self.current_relations:
            self.input_data.add_relation(RelationInput.from_unbound(relation, model))
        self.current_relations.clear()
        # Return dict because .model_validate will be called at root level
        return model if level == 1 or self.input_data.validation is None else params


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
        dtos: MappedGraphQLDTO[InputModel] | Sequence[MappedGraphQLDTO[InputModel]],
        _validation_: ValidationProtocol[InputModel] | None = None,
        **override: Any,
    ) -> None:
        self.max_level = 0
        self.relations: list[RelationInput] = []
        self.instances: list[InputModel] = []
        self.dtos: list[MappedDTO[InputModel]] = []
        self.validation = _validation_
        self.list_input = isinstance(dtos, Sequence)

        dtos = dtos if isinstance(dtos, Sequence) else [dtos]
        for index, dto in enumerate(dtos):
            mapped = dto.to_mapped(
                visitor=_InputVisitor(
                    self, is_update=dto.__strawchemy_purpose__ in ("update_by_pk_input", "update_by_filter_input")
                ),
                override=override,
            )
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
        level_relations = {relation.attribute.key for relation in self.relations if relation.level == _level}
        mapper = object_mapper(model)
        seen.add(self._model_identity(model))
        for relationship in mapper.relationships:
            if (
                relationship.key not in SQLAlchemyInspector.loaded_attributes(model)
                or relationship.key in level_relations
            ):
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
            if isinstance(relationship_value, (tuple, list)):
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
