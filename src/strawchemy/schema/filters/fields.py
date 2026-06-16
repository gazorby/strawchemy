"""Marker consumed by the filter factory for fine-grained filters.

`Strawchemy.filter_field()` returns a `FilterFieldMarker`; the field's annotation supplies the
comparison data type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from sqlalchemy import Dialect, Select
    from sqlalchemy.orm import DeclarativeBase

    from strawchemy.schema.factories._kwargs import StrawberryFieldKwargs

__all__ = ("VALID_JOINS", "CustomFilterApply", "FilterFieldMarker", "JoinStrategy")

JoinStrategy = Literal["exists", "in"]
VALID_JOINS: frozenset[str] = frozenset({"exists", "in"})


class CustomFilterApply(Protocol):
    """Callable accepted by ``filter_field(apply=...)``.

    Receives an isolated ``select(model)`` statement and the GraphQL-supplied value, plus the
    active ``dialect`` and ``model`` as keyword context, and returns the mutated statement. The
    transpiler passes exactly these keywords; a callback may still declare ``**other_context`` to
    accept them loosely (a ``**kwargs`` callable structurally satisfies this protocol).

    Note:
        The callback should only add filtering predicates (``.where(...)``) to the statement. It
        must not introduce joins or subqueries against the same ``model`` table: the statement is
        re-aliased and correlated by primary key, so a self-join onto ``model`` could be rewritten
        ambiguously.
    """

    def __call__(
        self,
        statement: Select[Any],
        value: Any,
        /,
        *,
        dialect: Dialect,
        model: type[DeclarativeBase],
    ) -> Select[Any]: ...


@dataclass(frozen=True, slots=True)
class FilterFieldMarker:
    """Sentinel describing one declared filter field."""

    ops: tuple[str, ...] | None = None
    """Selected GraphQL operator names for a restricted field, or ``None``."""
    apply: CustomFilterApply | None = None
    """Optional custom filter callable (see :class:`CustomFilterApply`)."""
    join: JoinStrategy = "exists"
    """Fold-back strategy for a custom filter (``"exists"`` or ``"in"``)."""
    field_kwargs: StrawberryFieldKwargs = field(default_factory=dict)
    """``strawberry.field`` arguments (name, description, metadata, …) for the generated field."""
