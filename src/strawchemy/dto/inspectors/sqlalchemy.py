from __future__ import annotations

import builtins
import contextlib
from dataclasses import MISSING as DATACLASS_MISSING
from dataclasses import Field, fields
from inspect import getmodule, signature
from typing import TYPE_CHECKING, Any, Optional, TypeVar, cast, get_args, get_origin, get_type_hints, override

from typing_extensions import TypeIs

from sqlalchemy import Column, SQLColumnExpression, event, inspect, orm, sql
from sqlalchemy.orm import (
    ColumnProperty,
    DeclarativeBase,
    Mapped,
    MappedAsDataclass,
    MappedSQLExpression,
    Mapper,
    QueryableAttribute,
    RelationshipDirection,
    RelationshipProperty,
    registry,
)
from strawchemy.constants import GEO_INSTALLED
from strawchemy.dto.base import TYPING_NS, DTOFieldDefinition, ModelInspector, Relation
from strawchemy.dto.constants import DTO_INFO_KEY
from strawchemy.dto.exceptions import ModelInspectorError
from strawchemy.dto.types import DTO_MISSING, DTOConfig, DTOFieldConfig, DTOMissingType, Purpose
from strawchemy.utils import is_type_hint_optional

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from types import ModuleType

    from shapely import Geometry

    from sqlalchemy.orm import MapperProperty
    from strawchemy.graph import Node


__all__ = ("SQLAlchemyInspector",)


T = TypeVar("T", bound=Any)


_shapely_geometry_map: dict[str, type[Geometry]] = {}

if GEO_INSTALLED:
    from shapely import (
        Geometry,
        GeometryCollection,
        LineString,
        MultiLineString,
        MultiPoint,
        MultiPolygon,
        Point,
        Polygon,
    )

    # Possible values that can be passed to geoalchemy2.types._GISType
    # https://geoalchemy-2.readthedocs.io/en/latest/types.html#geoalchemy2.types._GISType
    _shapely_geometry_map = {
        "GEOMETRY": Geometry,
        "POINT": Point,
        "LINESTRING": LineString,
        "POLYGON": Polygon,
        "MULTIPOINT": MultiPoint,
        "MULTILINESTRING": MultiLineString,
        "MULTIPOLYGON": MultiPolygon,
        "GEOMETRYCOLLECTION": GeometryCollection,
    }


_SQLA_NS = {**vars(orm), **vars(sql)}


class SQLAlchemyInspector(ModelInspector[DeclarativeBase, QueryableAttribute[Any]]):
    def __init__(self, registries: list[registry] | None = None) -> None:
        """Initialize internal state to keep track of generated DTOs."""
        self._mapped_classes_map: dict[str, type[DeclarativeBase]] = {}
        self._registries: list[registry] = registries or []
        self._model_modules: set[ModuleType] = set()
        self._model_type_hints: dict[type[DeclarativeBase], dict[str, Any]] = {}
        event.listens_for(Mapper, "after_mapper_constructed")(self._add_registry_listener)

    def _update_mapped_classes(self, mapper: Mapper[Any]) -> None:
        if mapper.registry not in self._registries:
            self._registries.append(mapper.registry)
        self._mapped_classes_map |= self._mapped_classes_from_registry(mapper.registry)

    def _add_registry_listener(self, mapper: Mapper[Any], class_: type[Any]) -> None:
        self._update_mapped_classes(mapper)

    def _mapped_classes_from_registry(self, registry: registry) -> dict[str, type[Any]]:
        return {m.class_.__name__: m.class_ for m in list(registry.mappers)}

    def _localns(self, type_: type[Any]) -> dict[str, Any]:
        """Build namespace for resolving forward refs of the given type.

        Args:
            type_: The type for which to build the namespace

        Returns:
            A dict suitable to pass to `get_type_hints`
            to resolve forward refs of the given model
        """
        localns: dict[str, Any] = {}
        localns.update(TYPING_NS)
        localns.update(_SQLA_NS)
        localns.update(self._mapped_classes)
        model_module = getmodule(type_)
        if model_module is not None:
            self._model_modules.add(model_module)
        for module in self._model_modules:
            localns.update(vars(module))
        return localns

    @classmethod
    def _dataclass_fields(cls, model: type[MappedAsDataclass]) -> dict[str, Field[Any]]:
        return {f.name: f for f in fields(model)}

    @property
    def _mapped_classes(self) -> dict[str, type[DeclarativeBase]]:
        """Get mapped classes across all added registries.

        Returns:
            A mapping of class name -> SQLAlchemy mapped class.
        """
        if not self._mapped_classes_map:
            for registry in self._registries:
                self._mapped_classes_map.update(self._mapped_classes_from_registry(registry))
        return self._mapped_classes_map

    def _uselist(self, elem: MapperProperty[Any]) -> bool:
        return bool(elem.uselist) if self._is_relationship(elem) else False

    def _is_init(self, model: type[DeclarativeBase], name: str) -> bool:
        if issubclass(model, MappedAsDataclass):
            field = self._dataclass_fields(model).get(name)
            return field.init if field is not None else False
        return True

    @classmethod
    def _is_relationship(
        cls, elem: MapperProperty[Any] | Column[Any] | RelationshipProperty[Any]
    ) -> TypeIs[RelationshipProperty[Any]]:
        return isinstance(elem, RelationshipProperty)

    @classmethod
    def _is_column(cls, elem: Any) -> TypeIs[ColumnProperty[Any] | Column[Any]]:
        return isinstance(elem, ColumnProperty | Column)

    @classmethod
    def _column_or_relationship(
        cls, attribute: MapperProperty[Any]
    ) -> Column[Any] | RelationshipProperty[Any] | SQLColumnExpression[Any]:
        try:
            return attribute.parent.mapper.columns[attribute.key]
        except KeyError:
            return attribute.parent.mapper.relationships[attribute.key]

    @classmethod
    def _defaults(
        cls, attribute: MapperProperty[Any]
    ) -> tuple[Any | DTOMissingType, Callable[..., Any] | DTOMissingType]:
        default, default_factory = DTO_MISSING, DTO_MISSING
        model = attribute.parent.class_
        element = cls._column_or_relationship(attribute)

        if (
            issubclass(model, MappedAsDataclass)
            and (field := cls._dataclass_fields(model).get(attribute.key))
            and field.default_factory is not DATACLASS_MISSING
        ):
            default_factory = field.default_factory

        default_factory = (
            getattr(element, "default_factory", DTO_MISSING) if default_factory is DTO_MISSING else default_factory
        )
        default = getattr(element, "default", DTO_MISSING) if default is DTO_MISSING else default

        if isinstance(element, Column):
            if not isinstance(default, DTOMissingType) and default is not None:
                if default.is_scalar:
                    default = default.arg
                elif default.is_callable:
                    default_callable = default.arg.__func__ if isinstance(default.arg, staticmethod) else default.arg
                    if (
                        # Eager test because inspect.signature() does not
                        # recognize builtins
                        hasattr(builtins, default_callable.__name__)
                        # If present, context contains information about the current
                        # statement and can be used to access values from other columns.
                        # As we can't reproduce such context in Pydantic, we don't want
                        # include a default_factory in that case.
                        or "context" not in signature(default_callable).parameters
                    ):
                        default_factory = lambda: default.arg({})  # noqa: E731
                    else:
                        default = DTO_MISSING
                else:
                    msg = "Unexpected default type"
                    raise ValueError(msg)
            elif default is None and not element.nullable:
                default = DTO_MISSING
        elif isinstance(element, RelationshipProperty) and default is DTO_MISSING and element.uselist:
            default_factory = list
        elif default is DTO_MISSING:
            default = None
        return default, default_factory

    def _field_config(self, elem: MapperProperty[Any]) -> DTOFieldConfig:
        config = cast(DTOFieldConfig, elem.class_attribute.info.get(DTO_INFO_KEY, DTOFieldConfig()))
        if isinstance(elem, MappedSQLExpression):
            config.purposes = {Purpose.READ}
        return config

    @classmethod
    def _resolve_model_type_hint(cls, type_: type[Any]) -> Any:
        type_hint = type_
        if get_origin(type_hint) is Mapped:
            (type_hint,) = get_args(type_hint)
        return type_hint

    def _relationship_required(self, prop: RelationshipProperty[Any]) -> bool:
        if prop.direction is RelationshipDirection.MANYTOONE:
            return any(not column.nullable for column in prop.local_columns)
        return False

    @classmethod
    def pk_attributes(cls, mapper: Mapper[Any]) -> list[QueryableAttribute[Any]]:
        return [mapper.attrs[column.key].class_attribute for column in mapper.primary_key]

    @override
    def get_type_hints(self, type_: Any, include_extras: bool = True) -> dict[str, Any]:
        if type_hints := self._model_type_hints.get(type_):
            return type_hints
        if issubclass(type_, DeclarativeBase):
            self._update_mapped_classes(inspect(type_))
        type_hints = get_type_hints(type_, localns=self._localns(type_), include_extras=include_extras)
        self._model_type_hints[type_] = type_hints
        return type_hints

    @override
    def field_definition(
        self, model_field: QueryableAttribute[T], dto_config: DTOConfig, type_hint: Any = DTO_MISSING
    ) -> DTOFieldDefinition[DeclarativeBase, QueryableAttribute[T]]:
        mapper = model_field.parent.mapper
        relation_model = None
        prop = mapper.attrs[model_field.key]
        elem = prop if isinstance(prop, MappedSQLExpression) else mapper.attrs[model_field.key]
        config = self._field_config(elem)
        if dto_config.exclude_defaults:
            default, default_factory = DTO_MISSING, DTO_MISSING
        else:
            default, default_factory = self._defaults(elem)
        uselist = self._uselist(elem)
        is_relation = self._is_relationship(elem)

        with contextlib.suppress(ModelInspectorError):
            relation_model = self.relation_model(prop.class_attribute)

        if type_hint is DTO_MISSING:
            type_hint = self.get_type_hints(mapper.class_).get(model_field.key, DTO_MISSING)

        type_hint = self._resolve_model_type_hint(type_hint)

        # If column type is a geoalchemy geometry type, override type hint with the corresponding shapely type
        if GEO_INSTALLED and (column_prop := mapper.columns.get(model_field.key)) is not None:
            from geoalchemy2 import Geometry

            if (
                isinstance(column_prop.type, Geometry)
                and column_prop.type.geometry_type is not None
                and column_prop.type.geometry_type in _shapely_geometry_map
            ):
                geo_type_hint = _shapely_geometry_map[column_prop.type.geometry_type]
                type_hint = Optional[geo_type_hint] if is_type_hint_optional(type_hint) else geo_type_hint  # noqa: UP007

        return DTOFieldDefinition(
            type_hint=type_hint,
            model=mapper.class_,
            model_field_name=model_field.key,
            uselist=uselist,
            config=config,
            dto_config=dto_config,
            init=self._is_init(mapper.class_, model_field.key),
            is_relation=is_relation,
            default=default,
            default_factory=default_factory,
            related_model=relation_model,
            _model_field=model_field,
        )

    @override
    def field_definitions(
        self, model: type[DeclarativeBase], dto_config: DTOConfig
    ) -> Generator[tuple[str, DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]]:
        mapper = inspect(model)
        columns, relationships = mapper.columns, mapper.relationships

        for key, type_hint in self.get_type_hints(model).items():
            if key not in columns and key not in relationships:
                continue
            mapper_property = mapper.attrs[key]
            yield key, self.field_definition(mapper_property.class_attribute, dto_config, type_hint=type_hint)

    @override
    def id_field_definitions(
        self, model: type[DeclarativeBase], dto_config: DTOConfig
    ) -> list[tuple[str, DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]]:
        mapper = inspect(model)
        primary_keys = {column.key for column in mapper.primary_key}

        return [
            (key, self.field_definition(mapper.attrs[key].class_attribute, dto_config, type_hint=type_hint))
            for key, type_hint in self.get_type_hints(model).items()
            if key in primary_keys
        ]

    @override
    def relation_model(self, model_field: QueryableAttribute[Any]) -> type[DeclarativeBase]:
        if self._is_relationship(model_field.property):
            return model_field.property.entity.mapper.class_
        msg = f"{model_field} is not a relationship"
        raise ModelInspectorError(msg)

    @override
    def model_field_type(self, field_definition: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]) -> Any:
        try:
            return field_definition.model_field.type.python_type
        except NotImplementedError:
            return super().model_field_type(field_definition)

    @override
    def relation_cycle(
        self,
        field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        node: Node[Relation[DeclarativeBase, Any], None],
    ) -> bool:
        if not self._is_relationship(field.model_field.property):
            return False
        parent_relationships: set[RelationshipProperty[Any]] = set()
        for parent in node.iter_parents():
            for relationship in parent.value.model.__mapper__.relationships:
                parent_relationships.add(relationship)
        return any(
            relationship in parent_relationships
            for relationship in field.model_field.property._reverse_property  # noqa: SLF001
        )

    @override
    def has_default(self, model_field: QueryableAttribute[Any]) -> bool:
        return any(default is not DTO_MISSING for default in self._defaults(model_field.property))

    @override
    def required(self, model_field: QueryableAttribute[Any]) -> bool:
        if self._is_column(model_field.property):
            return any(not column.nullable for column, _ in model_field.property.columns_to_assign)
        if self._is_relationship(model_field.property):
            return self._relationship_required(model_field.property)
        return False

    @override
    def is_foreign_key(self, model_field: QueryableAttribute[Any]) -> bool:
        return self._is_column(model_field.property) and any(
            column.foreign_keys for column in model_field.property.columns
        )

    @override
    def is_primary_key(self, model_field: QueryableAttribute[Any]) -> bool:
        return self._is_column(model_field.property) and any(
            column.primary_key for column in model_field.property.columns
        )

    @override
    def reverse_relation_required(self, model_field: QueryableAttribute[Any]) -> bool:
        if not self._is_relationship(model_field.property):
            return False
        return any(self._relationship_required(relationship) for relationship in model_field.property._reverse_property)  # noqa: SLF001
