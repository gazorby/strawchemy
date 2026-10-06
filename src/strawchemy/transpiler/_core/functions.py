"""SQL aggregate functions of a GraphQL aggregation, described as data and built on demand."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import Float, Integer, TypeDecorator, func, inspect
from sqlalchemy import distinct as sqla_distinct

from strawchemy.exceptions import TranspilingError
from strawchemy.utils.postgres import comparable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Dialect, Label
    from sqlalchemy.orm import QueryableAttribute
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql.operators import OperatorType
    from sqlalchemy.types import TypeEngine

    from strawchemy.repository.typing import FunctionGenerator
    from strawchemy.typing import QueryNodeType, SupportedDialect

__all__ = ("AggregateFunction", "build")


_FUNCTIONS: dict[str, FunctionGenerator] = {
    "count": func.count,
    "min": func.min,
    "max": func.max,
    "sum": func.sum,
    "avg": func.avg,
    "stddev_samp": func.stddev_samp,
    "stddev_pop": func.stddev_pop,
    "var_samp": func.var_samp,
    "var_pop": func.var_pop,
}
_STATISTICAL_FUNCTIONS = frozenset({"avg", "stddev_samp", "stddev_pop", "var_samp", "var_pop"})


class _IntegerResult(TypeDecorator[int]):
    impl = Integer
    cache_ok = True

    def process_result_value(self, value: Any, dialect: Dialect) -> int | None:
        return None if value is None else int(value)

    def coerce_compared_value(self, op: OperatorType | None, value: Any) -> TypeEngine[Any]:
        return self.impl_instance.coerce_compared_value(op, value)


def _result_type(name: str, attributes: Sequence[QueryableAttribute[Any]]) -> TypeEngine[Any] | None:
    """Returns the type matching the GraphQL output of an aggregate over integers, which drivers may give as ``Decimal``."""
    if name == "sum" and attributes[0].type.python_type is int:
        return _IntegerResult()
    if name in _STATISTICAL_FUNCTIONS and attributes[0].type.python_type is int:
        return Float()
    return None


@dataclass(frozen=True)
class AggregateFunction:
    """One SQL aggregate call, identified by ``node`` so that every stage asking for it shares one column."""

    node: QueryNodeType
    """The argument node when the call has exactly one argument, otherwise the function node."""
    name: str
    arguments: tuple[QueryNodeType, ...]
    """Nodes of the aggregated columns; empty for ``count()``."""
    distinct: bool

    @classmethod
    def for_selection(cls, function_node: QueryNodeType) -> tuple[AggregateFunction, ...]:
        """Returns the calls an aggregation field selects: one per argument node, or ``count()`` itself."""
        name = function_node.value.function(strict=True).function
        if name == "count":
            return (cls(node=function_node, name=name, arguments=(), distinct=False),)
        return tuple(cls(node=child, name=name, arguments=(child,), distinct=False) for child in function_node.children)

    @classmethod
    def for_filter(cls, function_node: QueryNodeType, *, distinct: bool | None = None) -> AggregateFunction:
        """Returns the single call a WHERE predicate on an aggregation field compares."""
        name = function_node.value.function(strict=True).function
        arguments = tuple(function_node.children)
        node = arguments[0] if len(arguments) == 1 else function_node
        return cls(node=node, name=name, arguments=arguments, distinct=bool(distinct))


def build(
    function: AggregateFunction, alias: AliasedClass[Any], dialect: SupportedDialect, over: bool = False
) -> Label[Any]:
    """Builds the labelled call with its arguments read from ``alias``.

    ``over`` makes it a window function over the whole result, for aggregations computed next to the rows.

    Raises:
        TranspilingError: If the function name is not a known aggregate.
    """
    if (sqla_function := _FUNCTIONS.get(function.name)) is None:
        msg = f"Unknown function {function.name}"
        raise TranspilingError(msg)
    alias_inspect = inspect(alias)
    attributes = [
        alias_inspect.mapper.attrs[argument.value.model_field_name].class_attribute.adapt_to_entity(alias_inspect)
        for argument in function.arguments
    ]
    result_type = _result_type(function.name, attributes)
    if function.distinct:
        attributes = [sqla_distinct(*[comparable(attribute, dialect) for attribute in attributes])]
    expression = sqla_function(*attributes) if result_type is None else sqla_function(*attributes, type_=result_type)
    if over:
        expression = expression.over()
    return expression.label(None)
