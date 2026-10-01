"""The ORDER BY of a level's rows: the client's, else ``default_order_by``, then the primary keys."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import inspect

from strawchemy.dto.strawberry import OrderByEnum, decompose_order_by
from strawchemy.exceptions import StrawchemyFieldError, TranspilingError
from strawchemy.transpiler._core.functions import AggregateFunction
from strawchemy.transpiler._core.pipeline import PassBase
from strawchemy.transpiler._core.render import clause_element, order_terms
from strawchemy.transpiler._core.rowset import OrderPriority

if TYPE_CHECKING:
    from sqlalchemy.sql import ColumnElement
    from sqlalchemy.sql.elements import UnaryExpression

    from strawchemy.transpiler._core.level import Level
    from strawchemy.transpiler._core.rowset import RowSet
    from strawchemy.typing import QueryNodeType

__all__ = ("Ordering",)


class Ordering(PassBase):
    """Orders a level's rows by the client's ordering, or by ``default_order_by`` and the primary keys without one.

    ``default_order_by`` applies to the root only. A relation level orders by its primary keys only when it orders,
    paginates or deduplicates its own rows; otherwise its keys order the parent query, which ``Relations`` adds.
    """

    def rows(self, level: Level, rows: RowSet) -> RowSet:
        db_features = level.context.db_features
        client: list[UnaryExpression[Any]] = []
        for node in level.request.order_by_nodes:
            column, rows = _order_column(level, node, rows)
            client.extend(order_terms(column, _direction(node), db_features))
        if client:
            return rows.with_order_by(OrderPriority.CLIENT, *client)
        if level.kind == "root" and level.context.default_order_by:
            rows = rows.with_order_by(OrderPriority.CLIENT, *_default_terms(level))
        if level.context.deterministic_ordering and (level.kind == "root" or level.request.orders_rows):
            keys = [term for key in level.primary_keys() for term in order_terms(key, OrderByEnum.ASC, db_features)]
            rows = rows.with_order_by(OrderPriority.DETERMINISTIC, *keys)
        return rows


def _direction(node: QueryNodeType) -> OrderByEnum:
    """Returns the direction the client gave ``node``.

    Raises:
        TranspilingError: If ``node`` has no direction.
    """
    if (direction := node.metadata.data.order_by) is None:
        msg = "Missing order by value"
        raise TranspilingError(msg)
    return direction


def _order_column(level: Level, node: QueryNodeType, rows: RowSet) -> tuple[ColumnElement[Any], RowSet]:
    """Returns the column ``node`` orders on, an aggregate or a column reached through to-one relations.

    Raises:
        TranspilingError: If ``node`` is a function leaf that no aggregate call of its function computes.
    """
    if not node.value.is_function:
        return level.path_column(node, rows)
    function_node = node.parent if node.value.is_function_arg else node
    assert function_node is not None
    calls = AggregateFunction.for_selection(function_node)
    if (function := next((call for call in calls if call.node is node), None)) is None:  # pragma: no cover  # defensive
        msg = f"No aggregate function orders on {node}"
        raise TranspilingError(msg)
    return level.aggregate(function, rows)


def _default_terms(level: Level) -> list[UnaryExpression[Any]]:
    """Builds the ORDER BY terms of ``default_order_by``, resolved against the level's alias.

    Raises:
        StrawchemyFieldError: If an expression references a column not on the level's model.
    """
    alias = inspect(level.alias)
    column_keys = {attribute.key for attribute in alias.mapper.column_attrs}
    terms: list[UnaryExpression[Any]] = []
    for expression in level.context.default_order_by:
        decomposed = decompose_order_by(expression)
        if decomposed.key not in column_keys:
            msg = f"`default_order_by` column '{decomposed.key}' is not a column of {level.request.model.__name__}"
            raise StrawchemyFieldError(msg)
        attribute = alias.mapper.attrs[decomposed.key].class_attribute.adapt_to_entity(alias)
        terms.extend(order_terms(clause_element(attribute), decomposed.order, level.context.db_features))
    return terms
