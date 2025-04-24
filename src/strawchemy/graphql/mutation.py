from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Generic, Literal, Self, TypeAlias, TypeVar, override

from pydantic import ValidationError

from strawchemy.dto.base import DTOFieldDefinition, MappedDTO, ModelFieldT, ModelT, ToMappedProtocol, VisitorProtocol
from strawchemy.dto.types import DTO_UNSET, DTOUnsetType

from .exceptions import InputValidationError

if TYPE_CHECKING:
    from collections.abc import Iterable

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
InputModel = TypeVar("InputModel")
RelationInputT = TypeVar("RelationInputT", bound=MappedDTO[Any])
RelationInputType: TypeAlias = Literal["set", "create", "add", "remove"]


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
        return self.create.to_mapped(visitor, level=level, override=override) if self.create else DTO_UNSET


class RequiredToOneInputMixin(ToOneInputMixin[T, RelationInputT]):
    @override
    def to_mapped(
        self, visitor: VisitorProtocol | None = None, override: dict[str, Any] | None = None, level: int = 0
    ) -> Any | DTOUnsetType:
        if not self.create and not self.set:
            msg = "Relation is required, you must set either `set` or `create`."
            raise ValueError(msg)
        return super().to_mapped(visitor, level=level, override=override)


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
        return (
            [dto.to_mapped(visitor, level=level, override=override) for dto in self.create]
            if self.create
            else DTO_UNSET
        )


class RequiredToManyUpdateInputMixin(ToMappedProtocol, Generic[T, RelationInputT]):
    add: list[T] | None
    create: list[RelationInputT] | None

    @override
    def to_mapped(
        self, visitor: VisitorProtocol | None = None, override: dict[str, Any] | None = None, level: int = 0
    ) -> list[Any] | DTOUnsetType:
        return (
            [dto.to_mapped(visitor, level=level, override=override) for dto in self.create]
            if self.create
            else DTO_UNSET
        )


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
        return super().to_mapped(visitor, level=level, override=override)


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
class _RelationInput(_UnboundRelationInput[ModelT, ModelFieldT], Generic[ModelT, ModelFieldT]):
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
class _InputVisitor(VisitorProtocol, Generic[ModelT, ModelFieldT]):
    input_data: Input[ModelT, ModelFieldT, Any]

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
    def model(self, parent: ToMappedProtocol, model_cls: type[ModelT], params: dict[str, Any], level: int) -> Any:
        if level == 1 and self.input_data.pydantic_model is not None:
            try:
                model = self.input_data.pydantic_model.model_validate(params).to_mapped()
            except ValidationError as error:
                raise InputValidationError(error) from error
        else:
            model = model_cls(**params)
        for relation in self.current_relations:
            assert relation.field.related_model
            relation_input = _RelationInput.from_unbound(relation, model)
            self.input_data.relations.append(relation_input)
        self.current_relations.clear()
        # Return dict because .model_validate will be called at root level
        if level != 1 and self.input_data.pydantic_model is not None:
            return params
        return model


@dataclass
class _FilteredRelationInput(Generic[ModelT, ModelFieldT]):
    relation: _RelationInput[ModelT, ModelFieldT]
    instance: ModelT


@dataclass
class LevelInput(Generic[ModelT, ModelFieldT]):
    inputs: list[_FilteredRelationInput[ModelT, ModelFieldT]] = field(default_factory=list)


class Input(Generic[ModelT, ModelFieldT, InputModel]):
    def __init__(
        self,
        dtos: MappedDTO[InputModel] | Sequence[MappedDTO[InputModel]],
        validation: type[MappedPydanticDTO[InputModel]] | None = None,
        **override: Any,
    ) -> None:
        self.max_level = 0
        self.relations: list[_RelationInput[ModelT, ModelFieldT]] = []
        self.instances: list[InputModel] = []
        self.pydantic_model = validation

        dtos = dtos if isinstance(dtos, Sequence) else [dtos]
        for index, dto in enumerate(dtos):
            mapped = dto.to_mapped(visitor=_InputVisitor(self), override=override)
            self.instances.append(mapped)
            for relation in self.relations:
                self.max_level = max(self.max_level, relation.level)
                if relation.input_index == -1:
                    relation.input_index = index

    def filter_by_level(
        self, relation_type: RelationType, input_types: Iterable[RelationInputType]
    ) -> list[LevelInput[ModelT, ModelFieldT]]:
        levels: list[LevelInput[ModelT, ModelFieldT]] = []
        level_range = (
            range(1, self.max_level + 1) if relation_type is RelationType.TO_MANY else range(self.max_level, 0, -1)
        )
        for level in level_range:
            level_input = LevelInput()
            for relation in self.relations:
                input_data: list[_FilteredRelationInput[ModelT, ModelFieldT]] = []
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
