from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import TypeDecorator, cast
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement
    from sqlalchemy.orm import QueryableAttribute
    from sqlalchemy.types import TypeEngine

    from strawchemy.typing import SupportedDialect

__all__ = ("as_jsonb", "comparable")

_DIALECT = postgresql.dialect()


def _postgres_type(expression: ColumnElement[Any] | QueryableAttribute[Any]) -> TypeEngine[Any]:
    impl = expression.type.dialect_impl(_DIALECT)
    while isinstance(impl, TypeDecorator):
        impl = impl.load_dialect_impl(_DIALECT)
    return impl


def as_jsonb(
    expression: ColumnElement[Any] | QueryableAttribute[Any],
) -> ColumnElement[Any] | QueryableAttribute[Any]:
    """Casts a JSON expression to ``jsonb`` when PostgreSQL stores it as ``json``.

    ``json`` has no equality operator and none of the ``jsonb`` operators or functions.
    """
    if isinstance(_postgres_type(expression), postgresql.JSONB):
        return expression
    return cast(expression, postgresql.JSONB)


def comparable(
    expression: ColumnElement[Any] | QueryableAttribute[Any], dialect: SupportedDialect
) -> ColumnElement[Any] | QueryableAttribute[Any]:
    """Casts a PostgreSQL ``json`` expression to ``jsonb``, which can be ordered and compared; leaves others as is."""
    if dialect == "postgresql" and isinstance(_postgres_type(expression), postgresql.JSON):
        return as_jsonb(expression)
    return expression
