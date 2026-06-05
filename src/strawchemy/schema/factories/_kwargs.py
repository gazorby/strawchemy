"""Reusable ``TypedDict``s for factory keyword argument groups.

These exist to collapse the long, repeated kwarg lists across the factory
methods in this package (`base.py`, `inputs.py`, `enum.py`, `types.py`).
They are intended to be used with ``typing_extensions.Unpack`` so call
sites still pass arguments by name and IDE / type checking completion still
works for individual fields.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from typing_extensions import TypedDict

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from sqlalchemy.orm import QueryableAttribute

    from strawchemy.dto.base import DTOFieldDefinition
    from strawchemy.dto.strawberry import BooleanFilterDTO, DTOKey, GraphQLFieldDefinition, OrderByDTO
    from strawchemy.dto.types import FieldSpec
    from strawchemy.schema.pagination import DefaultOffsetPagination
    from strawchemy.typing import GraphQLPurpose


__all__ = (
    "DTOConfigKwargs",
    "DecoratorKwargs",
    "FactoryMethodKwargs",
    "ForwardedFactoryKwargs",
    "InputDecoratorKwargs",
    "MakeInputKwargs",
    "RegistrationKwargs",
    "TypeDecoratorKwargs",
    "TypeWrapperKwargs",
)


class DTOConfigKwargs(TypedDict, total=False):
    """Args forwarded to ``config(...)`` to build a ``DTOConfig``."""

    include: FieldSpec | None
    exclude: FieldSpec | None
    partial: bool | None
    type_map: Mapping[Any, Any] | None
    aliases: Mapping[str, str] | None
    alias_generator: Callable[[str], str] | None


class RegistrationKwargs(TypedDict, total=False):
    """User-facing metadata consumed by ``registry.register_type`` / ``register_enum``.

    ``name`` is intentionally **not** here because it is positional in
    ``factory()`` and would shadow that parameter when spread via
    ``Unpack[]``. Methods that take ``name`` as a keyword declare it
    explicitly.

    Internal-only flags (``register_type``, ``user_defined``) live in
    ``ForwardedFactoryKwargs`` so they are not exposed via public
    decorators.
    """

    description: str | None
    directives: Sequence[object] | None
    override: bool


class TypeWrapperKwargs(TypedDict, total=False):
    """Args specific to ``.type()`` / ``_type_wrapper``."""

    paginate: FieldSpec | None
    default_pagination: DefaultOffsetPagination | None
    filter_input: type[BooleanFilterDTO] | None
    distinct_on: FieldSpec | None
    order: FieldSpec | type[OrderByDTO] | None
    query_hook: Any


class ForwardedFactoryKwargs(TypedDict, total=False):
    """Pure pass-through args between ``factory()`` overrides.

    Includes internal-only registration flags (``register_type``,
    ``user_defined``) — these are intentionally not on the public
    decorators.
    """

    parent_field_def: DTOFieldDefinition[Any, QueryableAttribute[Any]] | None
    current_node: Any
    if_no_fields: Literal["raise", "skip"]
    tags: set[str] | None
    backend_kwargs: dict[str, Any] | None
    no_cache: bool
    field_map: dict[DTOKey, GraphQLFieldDefinition] | None
    register_type: bool
    user_defined: bool


class DecoratorKwargs(DTOConfigKwargs, RegistrationKwargs, total=False):
    """Composite kwargs for plain ``.decorator()`` / ``.input()`` on enum factories."""


class TypeDecoratorKwargs(DTOConfigKwargs, RegistrationKwargs, TypeWrapperKwargs, total=False):
    """Composite kwargs for public ``.type()`` decorator."""


class InputDecoratorKwargs(DTOConfigKwargs, RegistrationKwargs, total=False):
    """Composite kwargs for public ``.input()`` decorator."""


class MakeInputKwargs(RegistrationKwargs, ForwardedFactoryKwargs, total=False):
    """Composite kwargs for ``make_input``."""

    base: type[Any] | None


class FactoryMethodKwargs(ForwardedFactoryKwargs, RegistrationKwargs, TypeWrapperKwargs, total=False):
    """Composite kwargs for ``factory()`` overrides.

    Bundles every kwarg that can flow through a ``factory()`` chain, so
    that subclass overrides can declare ``**kwargs: Unpack[FactoryMethodKwargs]``
    and remain Liskov-compatible with siblings that consume type-specific
    args (paginate, order, etc.) or registration metadata (description,
    directives) explicitly.
    """

    mode: GraphQLPurpose | None
    aggregations: bool
