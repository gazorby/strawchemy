from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import TypeDecorator, cast
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement
    from sqlalchemy.orm import QueryableAttribute

__all__ = ("as_jsonb",)

_DIALECT = postgresql.dialect()


def as_jsonb(
    expression: ColumnElement[Any] | QueryableAttribute[Any],
) -> ColumnElement[Any] | QueryableAttribute[Any]:
    """Casts a JSON expression to ``jsonb`` when PostgreSQL stores it as ``json``.

    ``json`` has no equality operator and none of the ``jsonb`` operators or functions.
    """
    impl = expression.type.dialect_impl(_DIALECT)
    while isinstance(impl, TypeDecorator):
        impl = impl.load_dialect_impl(_DIALECT)
    if isinstance(impl, postgresql.JSONB):
        return expression
    return cast(expression, postgresql.JSONB)
