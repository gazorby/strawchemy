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
from collections.abc import Generator, Sequence
from functools import cached_property
from typing import TYPE_CHECKING, Any, Literal, Optional, TypeAlias, TypeVar, get_type_hints

from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawberry.types.auto import StrawberryAuto
from strawberry.utils.typing import type_has_annotation
from typing_extensions import dataclass_transform, override

from strawberry import UNSET
from strawchemy.dto.base import DTOBackend, DTOBase, DTOFactory, DTOFieldDefinition, Relation
from strawchemy.dto.types import DTOAuto, DTOConfig, DTOScope, Purpose
from strawchemy.dto.utils import config
from strawchemy.exceptions import StrawchemyError
from strawchemy.graph import Node
from strawchemy.strawberry import typing as strawchemy_typing
from strawchemy.strawberry._instance import MapperModelInstance
from strawchemy.strawberry._registry import RegistryTypeInfo
from strawchemy.strawberry.dto import (
    BooleanFilterDTO,
    DTOKey,
    GraphQLFieldDefinition,
    MappedStrawberryGraphQLDTO,
    OrderByDTO,
    StrawchemyDTOAttributes,
    UnmappedStrawberryGraphQLDTO,
)
from strawchemy.strawberry.typing import GraphQLDTOT, GraphQLPurpose, MappedGraphQLDTO
from strawchemy.types import DefaultOffsetPagination
from strawchemy.utils import get_annotations

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping, Sequence

    from strawchemy import Strawchemy
    from strawchemy.dto.types import DTOConfig, ExcludeFields, IncludeFields
    from strawchemy.graph import Node
    from strawchemy.sqlalchemy.hook import QueryHook
    from strawchemy.sqlalchemy.inspector import SQLAlchemyGraphQLInspector
    from strawchemy.strawberry.typing import GraphQLType
    from strawchemy.validation.pydantic import MappedPydanticGraphQLDTO

__all__ = ("GraphQLDTOFactory",)

T = TypeVar("T", bound="DeclarativeBase")
PydanticGraphQLDTOT = TypeVar("PydanticGraphQLDTOT", bound="MappedPydanticGraphQLDTO[Any]")
MappedGraphQLDTOT = TypeVar("MappedGraphQLDTOT", bound="MappedGraphQLDTO[Any]")
UnmappedGraphQLDTOT = TypeVar("UnmappedGraphQLDTOT", bound="UnmappedStrawberryGraphQLDTO[Any]")
StrawchemyDTOT = TypeVar("StrawchemyDTOT", bound="StrawchemyDTOAttributes")

TypeScope: TypeAlias = Literal["schema"]


def type_scope_to_dto_scope(scope: TypeScope) -> DTOScope:
    return "global" if scope == "schema" else "dto"


@dataclasses.dataclass(eq=True, frozen=True)
class _ChildOptions:
    pagination: DefaultOffsetPagination | bool = False
    order_by: bool = False


class GraphQLDTOFactory(DTOFactory[DeclarativeBase, QueryableAttribute[Any], GraphQLDTOT]):
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

    def _type_info(
        self,
        dto: type[StrawchemyDTOT],
        dto_config: DTOConfig,
        current_node: Node[Relation[Any, GraphQLDTOT], None] | None,
        override: bool = False,
        user_defined: bool = False,
        child_options: _ChildOptions | None = None,
    ) -> RegistryTypeInfo:
        child_options = child_options or _ChildOptions()
        graphql_type = self.graphql_type(dto_config)
        model: type[DeclarativeBase] | None = dto.__dto_model__ if issubclass(dto, MappedStrawberryGraphQLDTO) else None  # type: ignore[reportGeneralTypeIssues]
        default_name = self.root_dto_name(model, dto_config, current_node) if model else dto.__name__
        type_info = RegistryTypeInfo(
            name=dto.__name__,
            default_name=default_name,
            graphql_type=graphql_type,
            override=override,
            user_defined=user_defined,
            pagination=DefaultOffsetPagination() if child_options.pagination is True else child_options.pagination,
            order_by=child_options.order_by,
            scope=dto_config.scope,
            model=model,
            exclude_from_scope=dto_config.exclude_from_scope,
        )
        if self._mapper.registry.name_clash(type_info) and current_node is not None:
            type_info = dataclasses.replace(
                type_info, name="".join(node.value.name for node in current_node.path_from_root())
            )
        return type_info

    def _register_type(
        self,
        dto: type[StrawchemyDTOT],
        dto_config: DTOConfig,
        current_node: Node[Relation[Any, GraphQLDTOT], None] | None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        override: bool = False,
        user_defined: bool = False,
        child_options: _ChildOptions | None = None,
    ) -> type[StrawchemyDTOT]:
        type_info = self._type_info(
            dto,
            dto_config,
            override=override,
            user_defined=user_defined,
            child_options=child_options,
            current_node=current_node,
        )
        self._raise_if_type_conflicts(type_info)
        return self._mapper.registry.register_type(
            dto, type_info, description=description or dto.__strawchemy_description__, directives=directives
        )

    def _check_model_instance_attribute(self, base: type[Any]) -> None:
        instance_attributes = [
            name
            for name, annotation in get_annotations(base).items()
            if type_has_annotation(annotation, MapperModelInstance)
        ]
        if len(instance_attributes) > 1:
            msg = f"{base.__name__} has multiple `MapperModelInstance` attributes: {instance_attributes}"
            raise StrawchemyError(msg)

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
        base.__annotations__ = base_annotations_copy
        return config

    def _raise_if_type_conflicts(self, type_info: RegistryTypeInfo) -> None:
        if self._mapper.registry.non_override_exists(type_info):
            msg = (
                f"""Type `{type_info.name}` cannot be auto generated because it's already declared."""
                """ You may want to set `override=True` on the existing type to use it everywhere."""
            )
            raise StrawchemyError(msg)

    def _config(
        self,
        purpose: Purpose,
        include: IncludeFields | None = None,
        exclude: ExcludeFields | None = None,
        partial: bool | None = None,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        scope: DTOScope | None = None,
        tags: set[str] | None = None,
    ) -> DTOConfig:
        return config(
            purpose,
            include=include,
            exclude=exclude,
            partial=partial,
            type_map=type_map,
            alias_generator=alias_generator,
            aliases=aliases,
            scope=scope,
            tags=tags,
        )

    def _type_wrapper(
        self,
        model: type[T],
        *,
        mode: GraphQLPurpose,
        include: IncludeFields | None = None,
        exclude: ExcludeFields | None = None,
        partial: bool | None = None,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        child_pagination: bool | DefaultOffsetPagination = False,
        child_order_by: bool = False,
        filter_input: type[BooleanFilterDTO] | None = None,
        order_by: type[OrderByDTO] | None = None,
        name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        query_hook: QueryHook[T] | list[QueryHook[T]] | None = None,
        override: bool = False,
        purpose: Purpose = Purpose.READ,
        scope: DTOScope | None = None,
    ) -> Callable[[type[Any]], type[GraphQLDTOT]]:
        def wrapper(class_: type[Any]) -> type[GraphQLDTOT]:
            dto_config = config(
                purpose,
                include=include,
                exclude=exclude,
                partial=partial,
                type_map=type_map,
                alias_generator=alias_generator,
                aliases=aliases,
                scope=scope,
                tags={mode},
            )
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
                child_options=_ChildOptions(pagination=child_pagination, order_by=child_order_by),
            )
            dto.__strawchemy_query_hook__ = query_hook
            if issubclass(dto, MappedStrawberryGraphQLDTO):
                dto.__strawchemy_filter__ = filter_input
                dto.__strawchemy_order_by__ = order_by
            dto.__strawchemy_purpose__ = mode
            return dto

        return wrapper

    def _input_wrapper(
        self,
        model: type[T],
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
            )
            dto = self.factory(
                model=model,
                dto_config=dto_config,
                base=class_,
                name=name,
                description=description,
                directives=directives,
                override=override,
                user_defined=True,
                mode=mode,
                **kwargs,
            )
            dto.__strawchemy_purpose__ = mode
            return dto

        return wrapper

    @cached_property
    def _namespace(self) -> dict[str, Any]:
        from strawchemy.sqlalchemy import hook  # noqa: PLC0415

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
        raise_if_no_fields: bool = False,
        *,
        field_map: dict[DTOKey, GraphQLFieldDefinition] | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]:
        field_map = field_map if field_map is not None else {}
        for field in super().iter_field_definitions(name, model, dto_config, base, node, raise_if_no_fields, **kwargs):
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
        parent_field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        current_node: Node[Relation[Any, GraphQLDTOT], None] | None = None,
        raise_if_no_fields: bool = False,
        tags: set[str] | None = None,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        override: bool = False,
        register_type: bool = True,
        user_defined: bool = False,
        **kwargs: Any,
    ) -> type[GraphQLDTOT]:
        field_map: dict[DTOKey, GraphQLFieldDefinition] = {}
        if base:
            self._check_model_instance_attribute(base)
            dto_config = self._resolve_config(dto_config, base)
        dto = super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            tags,
            backend_kwargs=backend_kwargs,
            field_map=field_map,
            **kwargs,
        )
        if not dto.__strawchemy_field_map__:
            dto.__strawchemy_field_map__ = field_map
        dto.__strawchemy_description__ = self.type_description()
        if register_type:
            return self._register_type(
                dto,
                dto_config,
                current_node=current_node,
                description=description,
                directives=directives,
                override=override,
                user_defined=user_defined,
            )
        return dto


class StrawchemyMappedFactory(GraphQLDTOFactory[MappedGraphQLDTOT]):
    def _root_input_config(self, model: type[Any], dto_config: DTOConfig, mode: GraphQLPurpose) -> DTOConfig:
        annotations_overrides: dict[str, Any] = {}
        partial = dto_config.partial
        exclude_defaults = dto_config.exclude_defaults
        id_fields = self.inspector.id_field_definitions(model, dto_config)
        # Add PKs for update/delete inputs
        if mode == "update_by_pk_input":
            if set(dto_config.exclude) & {name for name, _ in id_fields}:
                msg = (
                    "You cannot exclude primary key columns from an input type intended for create or update mutations"
                )
                raise StrawchemyError(msg)
            annotations_overrides |= {name: field.type_hint for name, field in id_fields}
        if mode == "update_by_filter_input":
            exclude_defaults = True
        if mode in {"update_by_pk_input", "update_by_filter_input"}:
            partial = True
        # Exclude default generated PKs for create inputs, if not explicitly included
        elif dto_config.include == "all":
            for name, field in id_fields:
                if self.inspector.has_default(field.model_field):
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
        model: type[T],
        *,
        include: IncludeFields | None = None,
        exclude: ExcludeFields | None = None,
        partial: bool | None = None,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        child_pagination: bool | DefaultOffsetPagination = False,
        child_order_by: bool = False,
        filter_input: type[BooleanFilterDTO] | None = None,
        order_by: type[OrderByDTO] | None = None,
        name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        query_hook: QueryHook[T] | list[QueryHook[T]] | None = None,
        override: bool = False,
        purpose: Purpose = Purpose.READ,
        scope: TypeScope | None = None,
        mode: GraphQLPurpose = "type",
    ) -> Callable[[type[Any]], type[MappedGraphQLDTO[T]]]:
        return self._type_wrapper(
            model=model,
            include=include,
            exclude=exclude,
            partial=partial,
            type_map=type_map,
            aliases=aliases,
            alias_generator=alias_generator,
            child_pagination=child_pagination,
            child_order_by=child_order_by,
            filter_input=filter_input,
            order_by=order_by,
            name=name,
            description=description,
            directives=directives,
            query_hook=query_hook,
            override=override,
            purpose=purpose,
            scope=type_scope_to_dto_scope(scope) if scope else None,
            mode=mode,
        )

    @dataclass_transform(order_default=True, kw_only_default=True)
    def input(
        self,
        model: type[T],
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
        scope: TypeScope | None = None,
        **kwargs: Any,
    ) -> Callable[[type[Any]], type[MappedGraphQLDTO[T]]]:
        return self._input_wrapper(
            model=model,
            include=include,
            exclude=exclude,
            partial=partial,
            type_map=type_map,
            aliases=aliases,
            alias_generator=alias_generator,
            name=name,
            description=description,
            directives=directives,
            override=override,
            purpose=purpose,
            mode=mode,
            scope=type_scope_to_dto_scope(scope) if scope else None,
            **kwargs,
        )

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        current_node: Node[Relation[Any, MappedGraphQLDTOT], None] | None = None,
        raise_if_no_fields: bool = False,
        tags: set[str] | None = None,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        mode: GraphQLPurpose | None = None,
        **kwargs: Any,
    ) -> type[MappedGraphQLDTOT]:
        if mode and dto_config.purpose is Purpose.WRITE:
            dto_config = self._root_input_config(model, dto_config, mode)
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
            mode=mode,
            **kwargs,
        )


class StrawchemyUnMappedDTOFactory(GraphQLDTOFactory[UnmappedGraphQLDTOT]):
    @dataclass_transform(order_default=True, kw_only_default=True)
    def input(
        self,
        model: type[T],
        *,
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
    ) -> Callable[[type[Any]], type[UnmappedStrawberryGraphQLDTO[T]]]:
        return self._input_wrapper(
            model=model,
            include=include,
            exclude=exclude,
            partial=partial,
            type_map=type_map,
            aliases=aliases,
            alias_generator=alias_generator,
            name=name,
            description=description,
            directives=directives,
            override=override,
            purpose=purpose,
            **kwargs,
        )

    @dataclass_transform(order_default=True, kw_only_default=True)
    def type(
        self,
        model: type[T],
        include: IncludeFields | None = None,
        exclude: ExcludeFields | None = None,
        partial: bool | None = None,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        child_pagination: bool | DefaultOffsetPagination = False,
        child_order_by: bool = False,
        filter_input: type[BooleanFilterDTO] | None = None,
        order_by: type[OrderByDTO] | None = None,
        name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        query_hook: QueryHook[T] | list[QueryHook[T]] | None = None,
        override: bool = False,
        purpose: Purpose = Purpose.READ,
        mode: GraphQLPurpose = "type",
    ) -> Callable[[type[Any]], type[UnmappedStrawberryGraphQLDTO[T]]]:
        return self._type_wrapper(
            model=model,
            include=include,
            exclude=exclude,
            partial=partial,
            type_map=type_map,
            aliases=aliases,
            alias_generator=alias_generator,
            child_pagination=child_pagination,
            child_order_by=child_order_by,
            filter_input=filter_input,
            order_by=order_by,
            name=name,
            description=description,
            directives=directives,
            query_hook=query_hook,
            override=override,
            purpose=purpose,
            mode=mode,
        )
