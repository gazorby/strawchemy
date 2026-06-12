"""This module defines factories for creating GraphQL DTOs (Data Transfer Objects).

It includes factories for:
- Aggregate DTOs
- Aggregate Filter DTOs
- OrderBy DTOs
- Type DTOs
- Filter DTOs
- Enum DTOs

These factories are used to generate DTOs that are compatible with GraphQL schemas,
allowing for efficient data transfer and filtering in GraphQL queries.
"""

from __future__ import annotations

import dataclasses
import warnings
from enum import Enum
from functools import cached_property
from inspect import getmembers
from typing import TYPE_CHECKING, Any, ForwardRef, Literal, Optional, TypeAlias, TypeVar, get_type_hints

from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawberry import UNSET
from strawberry.schema.types.scalar import DEFAULT_SCALAR_REGISTRY
from strawberry.types import has_object_definition
from strawberry.types.auto import StrawberryAuto
from strawberry.types.scalar import ScalarDefinition, ScalarWrapper
from strawberry.utils.typing import type_has_annotation
from typing_extensions import Self, Unpack, dataclass_transform, override

from strawchemy import typing as strawchemy_typing
from strawchemy.dto.base import DTOBackend, DTOBase, DTOFactory, DTOFieldDefinition, Relation
from strawchemy.dto.strawberry import (
    BooleanFilterDTO,
    DTOKey,
    EnumDTO,
    GraphQLFieldDefinition,
    MappedStrawberryGraphQLDTO,
    OrderByDTO,
    StrawchemyObject,
    UnmappedStrawberryGraphQLDTO,
)
from strawchemy.dto.types import DTOAuto, DTOConfig, DTOScope, DTOSkip, Purpose, is_fields_iterable
from strawchemy.dto.utils import config
from strawchemy.exceptions import EmptyDTOError, StrawchemyError, StrawchemyFieldError
from strawchemy.instance import MapperModelInstance
from strawchemy.schema.field import StrawchemyField
from strawchemy.transpiler import hook
from strawchemy.typing import GraphQLDTOT, GraphQLPurpose, GraphQLType, MappedGraphQLDTO
from strawchemy.utils.annotation import get_annotations, inner_types, try_resolve_forwardref

if TYPE_CHECKING:
    import builtins
    from collections.abc import Callable, Generator, Mapping, Sequence

    from strawchemy import Strawchemy
    from strawchemy.dto.inspectors import SQLAlchemyGraphQLInspector
    from strawchemy.dto.types import FieldSelector, FieldSpec
    from strawchemy.schema.factories._kwargs import (
        InputDecoratorKwargs,
        MakeInputKwargs,
        TypeDecoratorKwargs,
    )
    from strawchemy.schema.pagination import DefaultOffsetPagination
    from strawchemy.transpiler.hook import QueryHook
    from strawchemy.utils.graph import Node
    from strawchemy.validation.pydantic import MappedPydanticGraphQLDTO

__all__ = ("GraphQLFactory", "StrawchemyMappedFactory", "StrawchemyUnMappedFactory")

T = TypeVar("T", bound="DeclarativeBase")
PydanticGraphQLDTOT = TypeVar("PydanticGraphQLDTOT", bound="MappedPydanticGraphQLDTO[Any]")
MappedGraphQLDTOT = TypeVar("MappedGraphQLDTOT", bound="MappedGraphQLDTO[Any]")
UnmappedGraphQLDTOT = TypeVar("UnmappedGraphQLDTOT", bound="UnmappedStrawberryGraphQLDTO[Any]")
StrawchemyDTOT = TypeVar("StrawchemyDTOT", bound="StrawchemyObject")

TypeScope: TypeAlias = Literal["schema"]


@dataclasses.dataclass(eq=True, frozen=True)
class ChildOptions:
    pagination: DefaultOffsetPagination | bool = False
    order_by: bool = False


class GraphQLFactory(DTOFactory[DeclarativeBase, QueryableAttribute[Any], GraphQLDTOT]):
    inspector: SQLAlchemyGraphQLInspector

    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[GraphQLDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(mapper.config.inspector, backend, handle_cycles, type_map, **kwargs)
        self._mapper = mapper

    def _check_model_instance_attribute(self, base: type[Any]) -> None:
        instance_attributes = [
            name
            for name, annotation in get_annotations(base).items()
            if type_has_annotation(annotation, MapperModelInstance)
        ]
        if len(instance_attributes) > 1:
            msg = f"{base.__name__} has multiple `MapperModelInstance` attributes: {instance_attributes}"
            raise StrawchemyError(msg)

    def is_graphql_mappable(self, annotation: Any, namespace: Mapping[str, Any] | None = None) -> bool:
        """True if `annotation` resolves to a GraphQL output/input type via Strawberry."""
        namespace = self.type_hint_namespace() if namespace is None else namespace
        return all(self._is_graphql_mappable(leaf, namespace) for leaf in inner_types(annotation))

    def _is_graphql_mappable(self, annotation: Any, namespace: Mapping[str, Any]) -> bool:
        # Forward references / string annotations: try to resolve and re-check; assume mappable
        # if resolution fails (e.g. an as-yet-unregistered relation reference).
        if isinstance(annotation, (str, ForwardRef)):
            resolved = try_resolve_forwardref(annotation, namespace)
            return True if resolved is None else self.is_graphql_mappable(resolved, namespace)
        # Strawberry scalar objects (e.g. Strawchemy's Date/DateTime/Interval/Time/GeoJSON, used
        # directly as annotations) are unhashable, so test these before any registry membership lookup.
        if (
            self._is_strawberry_scalar(annotation)
            or annotation in (None, Self)
            or isinstance(annotation, TypeVar)
            or has_object_definition(annotation)
            or (isinstance(annotation, type) and issubclass(annotation, Enum))
        ):
            return True
        try:
            return annotation in DEFAULT_SCALAR_REGISTRY
        except TypeError:  # unhashable and not a known scalar object
            return False

    @staticmethod
    def _is_strawberry_scalar(leaf: Any) -> bool:
        return (
            isinstance(leaf, (ScalarWrapper, ScalarDefinition)) or getattr(leaf, "_scalar_definition", None) is not None
        )

    @override
    def _resolve_basic_type(
        self, field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]], dto_config: DTOConfig
    ) -> Any:
        resolved = super()._resolve_basic_type(field, dto_config)
        if self._mapper.config.strict:
            return resolved
        overridden = (
            field.has_type_override or field.type_hint in dto_config.type_overrides or field.type_hint in self.type_map
        )
        if overridden or self.is_graphql_mappable(resolved):
            return resolved
        warnings.warn(
            f"Skipping {field.model.__name__}.{field.model_field_name}: no GraphQL mapping for {resolved!r}",
            stacklevel=2,
        )
        return DTOSkip

    def _resolve_config(self, dto_config: DTOConfig, base: type[Any]) -> DTOConfig:
        config = dto_config.with_base_annotations(base)
        try:
            base_annotations = get_type_hints(base, include_extras=True)
        except NameError:
            base_annotations = get_annotations(base)
        base_annotations_copy = base_annotations.copy()
        for name, annotation in base_annotations.items():
            if type_has_annotation(annotation, StrawberryAuto):
                config.annotation_overrides[name] = DTOAuto
                base_annotations_copy.pop(name)
        # Reverse-map model_field aliases so the DTO factory finds the annotation
        # override under the model field name and includes the aliased field.
        # A `model_field` declaration always wins: the aliased model field is added
        # to the include set even if it appears in an explicit `exclude`.
        reverse_aliases = {schema_name: model_name for model_name, schema_name in config.aliases.items()}
        extra_include: set[FieldSelector] = set()
        for schema_name, model_name in reverse_aliases.items():
            if schema_name in base_annotations and model_name not in config.annotation_overrides:
                config.annotation_overrides[model_name] = base_annotations[schema_name]
                extra_include.add(model_name)
        if extra_include:
            config = config | DTOConfig(config.purpose, include=extra_include)
        base.__annotations__ = base_annotations_copy
        return config

    def collect_field_model_aliases(
        self,
        class_: type[Any],
        model: type[DeclarativeBase],
        dto_config: DTOConfig,
    ) -> dict[str, str]:
        """Build an alias delta from a class body's ``model_field`` declarations.

        Scans ``class_`` for ``StrawchemyField``s that carry a ``model_field`` and
        maps each model field name to the schema attribute name it is declared
        under, so the existing alias machinery renders the field under its schema
        name while preserving the model linkage for data resolution.

        Args:
            class_: The decorated class whose body is scanned for declared fields.
            model: The SQLAlchemy model the type maps to.
            dto_config: Config used to enumerate the model's fields (via the
                inspector).

        Returns:
            A mapping of model field name to schema field name for every declared
            field that carries a ``model_field``.

        Raises:
            StrawchemyFieldError: If a ``model_field`` target is not a mapped
                attribute of ``model``, or if two declared fields target the same
                model field.
        """
        valid_names = {name for name, _ in self.inspector.field_definitions(model, dto_config)}
        alias_delta: dict[str, str] = {}

        for attr_name, value in getmembers(class_):
            if not isinstance(value, StrawchemyField):
                continue
            target = value.model_field
            if target is None:
                continue
            if target not in valid_names:
                msg = f"Model field '{target}' not found on {model.__name__}"
                raise StrawchemyFieldError(msg)
            if attr_name in valid_names and attr_name != target:
                msg = (
                    f"Schema field '{attr_name}' shadows a different model field on "
                    f"{model.__name__}; rename the schema field or alias that column too"
                )
                raise StrawchemyFieldError(msg)
            if target in alias_delta:
                msg = (
                    f"Model field '{target}' is targeted by multiple schema fields: "
                    f"'{alias_delta[target]}' and '{attr_name}'"
                )
                raise StrawchemyFieldError(msg)
            alias_delta[target] = attr_name

        return alias_delta

    def _config(
        self,
        purpose: Purpose,
        include: FieldSpec | None = None,
        exclude: FieldSpec | None = None,
        partial: bool | None = None,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        scope: DTOScope | None = None,
        tags: set[str] | None = None,
        model: type[DeclarativeBase] | None = None,
        class_: type[Any] | None = None,
    ) -> DTOConfig:
        if aliases is not None:
            warnings.warn(
                "The `aliases` parameter is deprecated; use field-level `strawchemy.field(model_field=...)` instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        dto_config = (
            config(
                purpose,
                include=include,
                exclude=exclude,
                partial=partial,
                type_map=type_map,
                aliases=aliases,
                alias_generator=alias_generator,
                scope=scope,
                tags=tags,
            )
            | self._mapper.config.field_config
        )
        if model is not None and class_ is not None:
            delta = self.collect_field_model_aliases(class_, model, dto_config)
            if delta:
                dto_config = dto_config | DTOConfig(dto_config.purpose, aliases=delta)
        return dto_config

    def _type_order_by(
        self, model: type[DeclarativeBase], include: FieldSpec | type[OrderByDTO] | None = None
    ) -> type[OrderByDTO] | None:
        order_include = self._mapper.config.order_by if include is None else include
        if is_fields_iterable(order_include):
            try:
                order_by_input = self._mapper.order_by_factory.make_input(
                    model=model,
                    mode="order_by",
                    dto_config=DTOConfig(
                        Purpose.READ,
                        partial=True,
                        include=order_include,
                        global_include=self._mapper.config.order_by or (),
                    ),
                    if_no_fields="raise",
                    no_cache=True,
                )
            except EmptyDTOError:
                order_by_input = None
        else:
            order_by_input = order_include
        return order_by_input

    def _type_distinct_on(
        self, model: type[DeclarativeBase], include: FieldSpec | type[EnumDTO] | None = None
    ) -> type[EnumDTO] | None:
        distinct_on_include = self._mapper.config.distinct_on if include is None else include
        if is_fields_iterable(distinct_on_include):
            try:
                distinct_on_input = self._mapper.distinct_on_enum_factory.factory(
                    model=model,
                    dto_config=DTOConfig(
                        Purpose.READ,
                        partial=True,
                        include=distinct_on_include,
                        global_include=self._mapper.config.distinct_on or (),
                    ),
                    if_no_fields="raise",
                    no_cache=True,
                )
            except EmptyDTOError:
                distinct_on_input = None
        else:
            distinct_on_input = distinct_on_include
        return distinct_on_input

    def _type_wrapper(
        self,
        model: type[T],
        *,
        mode: GraphQLPurpose,
        include: FieldSpec | None = None,
        exclude: FieldSpec | None = None,
        partial: bool | None = None,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        paginate: FieldSpec | None = None,
        distinct_on: FieldSpec | None = None,
        default_pagination: None | DefaultOffsetPagination = None,
        filter_input: type[BooleanFilterDTO] | None = None,
        order: FieldSpec | type[OrderByDTO] | None = None,
        name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        query_hook: QueryHook[T] | list[QueryHook[T]] | None = None,
        override: bool = False,
        purpose: Purpose = Purpose.READ,
        scope: DTOScope | None = None,
    ) -> Callable[[type[Any]], type[GraphQLDTOT]]:
        def wrapper(class_: type[Any]) -> type[GraphQLDTOT]:
            dto_config = self._config(
                purpose,
                include=include,
                exclude=exclude,
                partial=partial,
                type_map=type_map,
                aliases=aliases,
                alias_generator=alias_generator,
                scope=scope,
                tags={mode},
                model=model,
                class_=class_,
            )

            order_by_input = self._type_order_by(model, order)
            distinct_on_input = self._type_distinct_on(model, distinct_on)

            dto = self.factory(
                model=model,
                dto_config=dto_config,
                base=class_,
                name=name,
                description=description,
                directives=directives,
                query_hook=query_hook,
                override=override,
                user_defined=True,
                mode=mode,
                paginate=self._mapper.config.pagination if paginate is None else paginate,
                order=self._mapper.config.order_by if order is None else order,
                distinct_on=self._mapper.config.distinct_on if distinct_on is None else distinct_on,
                default_pagination=default_pagination,
            )
            strawchemy_def = dto.__strawchemy_definition__
            strawchemy_def.query_hook = query_hook
            if issubclass(dto, MappedStrawberryGraphQLDTO):
                if order_by_input is not None:
                    strawchemy_def.order_by = order_by_input
                if distinct_on_input is not None:
                    strawchemy_def.distinct_on = distinct_on_input
                if filter_input is not None:
                    strawchemy_def.filter = filter_input
            strawchemy_def.purpose = mode
            return dto

        return wrapper

    def _input_wrapper(
        self,
        model: type[T],
        *,
        mode: GraphQLPurpose,
        include: FieldSpec | None = None,
        exclude: FieldSpec | None = None,
        partial: bool | None = None,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        override: bool = False,
        purpose: Purpose = Purpose.WRITE,
        scope: DTOScope | None = None,
        **kwargs: Any,
    ) -> Callable[[type[Any]], type[GraphQLDTOT]]:
        def wrapper(class_: type[Any]) -> type[GraphQLDTOT]:
            dto_config = self._config(
                purpose,
                include=include,
                exclude=exclude,
                partial=partial,
                type_map=type_map,
                alias_generator=alias_generator,
                aliases=aliases,
                scope=scope,
                tags={mode},
                model=model,
                class_=class_,
            )
            return self.make_input(
                model=model,
                dto_config=dto_config,
                mode=mode,
                name=name,
                description=description,
                directives=directives,
                override=override,
                base=class_,
                **kwargs,
            )

        return wrapper

    @classmethod
    def _type_scope_to_dto_scope(cls, scope: TypeScope) -> DTOScope:
        return "global" if scope == "schema" else "dto"

    def make_input(
        self,
        model: type[T],
        *,
        mode: GraphQLPurpose,
        dto_config: DTOConfig,
        name: str | None = None,
        **kwargs: Unpack[MakeInputKwargs],
    ) -> type[GraphQLDTOT]:
        dto = self.factory(model=model, dto_config=dto_config, name=name, mode=mode, **kwargs)
        dto.__strawchemy_definition__.purpose = mode
        return dto

    @cached_property
    def _namespace(self) -> dict[str, Any]:
        return vars(strawchemy_typing) | vars(hook)

    @classmethod
    def graphql_type(cls, dto_config: DTOConfig) -> GraphQLType:
        return "input" if dto_config.purpose is Purpose.WRITE else "object"

    def type_description(self) -> str:
        return "GraphQL type"

    @override
    def type_hint_namespace(self) -> dict[str, Any]:
        return super().type_hint_namespace() | self._namespace

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[T],
        dto_config: DTOConfig,
        base: type[DTOBase[DeclarativeBase]] | None,
        node: Node[Relation[DeclarativeBase, GraphQLDTOT], None],
        if_no_fields: Literal["raise", "skip"] = "skip",
        *,
        field_map: dict[DTOKey, GraphQLFieldDefinition] | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]:
        field_map = field_map if field_map is not None else {}
        for field in super().iter_field_definitions(name, model, dto_config, base, node, if_no_fields, **kwargs):
            key = DTOKey.from_dto_node(node)
            graphql_field = GraphQLFieldDefinition.from_field(field)
            yield graphql_field
            field_map[key + field.name] = graphql_field

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        *,
        parent_field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        current_node: Node[Relation[Any, GraphQLDTOT], None] | None = None,
        if_no_fields: Literal["raise", "skip"] = "skip",
        tags: set[str] | None = None,
        backend_kwargs: dict[str, Any] | None = None,
        no_cache: bool = False,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        override: bool = False,
        register_type: bool = True,
        user_defined: bool = False,
        **kwargs: Any,
    ) -> type[GraphQLDTOT]:
        field_map: dict[DTOKey, GraphQLFieldDefinition] = {}
        if not user_defined and no_cache:
            name = self.root_dto_name(model, dto_config, current_node) if name is None else name
            name = self._mapper.registry.uniquify_name(self.graphql_type(dto_config), name)
        if base:
            self._check_model_instance_attribute(base)
            dto_config = self._resolve_config(dto_config, base)

        dto: type[GraphQLDTOT] = super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def=parent_field_def,
            current_node=current_node,
            if_no_fields=if_no_fields,
            tags=tags,
            backend_kwargs=backend_kwargs,
            no_cache=no_cache,
            field_map=field_map,
            **kwargs,
        )
        if not dto.__strawchemy_definition__.field_map:
            dto.__strawchemy_definition__.field_map = field_map
        dto.__strawchemy_definition__.description = self.type_description()

        if register_type:
            return self._mapper.registry.register_type(
                dto,
                graphql_type=self.graphql_type(dto_config),
                dto_config=dto_config,
                current_node=current_node,
                description=description,
                directives=directives,
                override=override,
                user_defined=user_defined,
                default_name=self.root_dto_name(model, dto_config),
            )
        return dto


class StrawchemyMappedFactory(GraphQLFactory[MappedGraphQLDTOT]):
    def _root_input_config(self, model: builtins.type[Any], dto_config: DTOConfig, mode: GraphQLPurpose) -> DTOConfig:
        annotations_overrides: dict[str, Any] = {}
        partial = dto_config.partial
        exclude_defaults = dto_config.exclude_defaults
        id_fields = self.inspector.id_field_definitions(model, dto_config)
        # Add PKs for update/delete inputs
        if mode == "update_by_pk_input":
            if set(dto_config.excluded_fields) & {name for name, _ in id_fields}:
                msg = (
                    "You cannot exclude primary key columns from an input type intended for create or update mutations"
                )
                raise StrawchemyError(msg)
            annotations_overrides |= {name: field.type_hint for name, field in id_fields}
        if mode == "update_by_filter_input":
            exclude_defaults = True
        if mode in {"update_by_pk_input", "update_by_filter_input"}:
            partial = True
        # Make create-input columns optional when their value can be omitted:
        # a primary key with a default (generated PK), or any column whose value
        # is generated by the database (SQL expression or sequence default).
        elif dto_config.include == "all":
            for name, field in self.inspector.field_definitions(model, dto_config):
                model_field = field.model_field
                if field in dto_config.included_fields and (
                    self.inspector.has_db_resolved_default(model_field)
                    or (self.inspector.is_primary_key(model_field) and self.inspector.has_default(model_field))
                ):
                    annotations_overrides[name] = Optional[field.type_hint]
        return dto_config.copy_with(
            annotation_overrides=annotations_overrides,
            partial=partial,
            partial_default=UNSET,
            unset_sentinel=UNSET,
            exclude_defaults=exclude_defaults,
        )

    @dataclass_transform(order_default=True, kw_only_default=True)
    def type(
        self,
        model: builtins.type[T],
        *,
        name: str | None = None,
        purpose: Purpose = Purpose.READ,
        scope: TypeScope | None = None,
        mode: GraphQLPurpose = "type",
        **kwargs: Unpack[TypeDecoratorKwargs],
    ) -> Callable[[builtins.type[Any]], builtins.type[MappedGraphQLDTO[T]]]:
        return self._type_wrapper(
            model=model,
            name=name,
            purpose=purpose,
            scope=self._type_scope_to_dto_scope(scope) if scope else None,
            mode=mode,
            **kwargs,
        )

    @dataclass_transform(order_default=True, kw_only_default=True)
    def input(
        self,
        model: builtins.type[T],
        *,
        mode: GraphQLPurpose,
        name: str | None = None,
        purpose: Purpose = Purpose.WRITE,
        scope: TypeScope | None = None,
        **kwargs: Unpack[InputDecoratorKwargs],
    ) -> Callable[[builtins.type[Any]], builtins.type[MappedGraphQLDTO[T]]]:
        return self._input_wrapper(
            model=model,
            name=name,
            purpose=purpose,
            mode=mode,
            scope=self._type_scope_to_dto_scope(scope) if scope else None,
            **kwargs,
        )

    @override
    def factory(
        self,
        model: builtins.type[T],
        dto_config: DTOConfig,
        base: builtins.type[Any] | None = None,
        name: str | None = None,
        *,
        mode: GraphQLPurpose | None = None,
        **kwargs: Any,
    ) -> builtins.type[MappedGraphQLDTOT]:
        if mode and dto_config.purpose is Purpose.WRITE:
            dto_config = self._root_input_config(model, dto_config, mode)
        return super().factory(model, dto_config, base, name, mode=mode, **kwargs)


class StrawchemyUnMappedFactory(GraphQLFactory[UnmappedGraphQLDTOT]):
    @dataclass_transform(order_default=True, kw_only_default=True)
    def input(
        self,
        model: builtins.type[T],
        *,
        mode: GraphQLPurpose = "create_input",
        name: str | None = None,
        purpose: Purpose = Purpose.WRITE,
        scope: TypeScope | None = None,
        **kwargs: Unpack[InputDecoratorKwargs],
    ) -> Callable[[builtins.type[Any]], builtins.type[UnmappedStrawberryGraphQLDTO[T]]]:
        return self._input_wrapper(model=model, mode=mode, name=name, purpose=purpose, **kwargs)

    @dataclass_transform(order_default=True, kw_only_default=True)
    def type(
        self,
        model: builtins.type[T],
        *,
        name: str | None = None,
        purpose: Purpose = Purpose.READ,
        mode: GraphQLPurpose = "type",
        **kwargs: Unpack[TypeDecoratorKwargs],
    ) -> Callable[[builtins.type[Any]], builtins.type[UnmappedStrawberryGraphQLDTO[T]]]:
        return self._type_wrapper(model=model, name=name, purpose=purpose, mode=mode, **kwargs)
