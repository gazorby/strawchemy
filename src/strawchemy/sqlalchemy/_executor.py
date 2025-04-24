"""Module for executing SQLAlchemy queries and converting results to QueryResult.

This module defines the QueryExecutor class, which provides methods for
executing SQLAlchemy queries and converting the results into QueryResult
objects.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, Self

from strawchemy.dto import ModelT

from .exceptions import QueryResultError
from .typing import AnyAsyncSession, AnySyncSession, DeclarativeT

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Sequence

    from sqlalchemy import Label, Result, Select, StatementLambdaElement
    from strawchemy.graphql.dto import QueryNode

    from ._scope import QueryScope


__all__ = ("AsyncQueryExecutor", "NodeResult", "QueryExecutor", "SyncQueryExecutor")


@dataclass
class NodeResult(Generic[ModelT]):
    model: ModelT
    computed_values: dict[str, Any]
    node_key: Callable[[QueryNode[Any, Any]], str]

    def value(self, key: QueryNode[Any, Any]) -> Any:
        if key.value.is_computed:
            return self.computed_values[self.node_key(key)]
        return getattr(self.model, key.value.model_field_name)

    def copy_with(self, model: Any) -> Self:
        return dataclasses.replace(self, model=model)


@dataclass
class QueryResult(Generic[ModelT]):
    """Represents the result of a GraphQL query.

    This class holds the nodes (data objects) returned by the query,
    computed values for each node, and computed values for the query itself.

    Attributes:
        nodes: A sequence of data objects of type ModelT.
        node_computed_values: A sequence of dictionaries containing computed
            values for each node.
        query_computed_values: A defaultdict containing computed values for
            the query.
    """

    node_key: Callable[[QueryNode[Any, Any]], str] = lambda key: str(key)
    nodes: Sequence[ModelT] = dataclasses.field(default_factory=list)
    node_computed_values: Sequence[dict[str, Any]] = dataclasses.field(default_factory=list)
    query_computed_values: defaultdict[str, Any] = dataclasses.field(default_factory=lambda: defaultdict(lambda: None))

    def __post_init__(self) -> None:
        if not self.node_computed_values:
            self.node_computed_values = [{} for _ in range(len(self.nodes))]

    def __iter__(self) -> Generator[NodeResult[ModelT]]:
        for model, compiled_values in zip(self.nodes, self.node_computed_values, strict=True):
            yield NodeResult(model, compiled_values, self.node_key)

    def value(self, key: QueryNode[Any, Any]) -> Any:
        return self.query_computed_values[self.node_key(key)]

    def one(self) -> NodeResult[ModelT]:
        if len(self.nodes) != 1 or len(self.node_computed_values) != 1:
            msg = f"Expected one item, got {len(self.nodes)}"
            raise QueryResultError(msg)
        return NodeResult(self.nodes[0], self.node_computed_values[0], self.node_key)

    def one_or_none(self) -> NodeResult[ModelT] | None:
        try:
            return self.one()
        except QueryResultError:
            return None


@dataclass
class QueryExecutor(Generic[DeclarativeT]):
    """Executes SQLAlchemy queries and converts the results into QueryResult objects.

    This class provides methods for executing SQLAlchemy queries and converting
    the results into QueryResult objects. It supports applying unique constraints,
    handling root aggregations, and fetching results as either a list or a single item.
    """

    base_statement: Select[tuple[DeclarativeT]]
    scope: QueryScope[Any]
    apply_unique: bool = False
    root_aggregation_functions: list[Label[Any]] = dataclasses.field(default_factory=list)
    execution_options: dict[str, Any] | None = None

    def _to_query_result(
        self, result: Result[tuple[DeclarativeT, Any]], fetch: Literal["one_or_none", "all"]
    ) -> QueryResult[DeclarativeT]:
        """Converts a SQLAlchemy result to a QueryResult object.

        Args:
            result: The SQLAlchemy result to convert.
            fetch: Whether to fetch one or all results.

        Returns:
            A QueryResult object containing the nodes and computed values.
        """
        nodes: list[DeclarativeT] = []
        computed: list[dict[str, Any]] = []
        if self.apply_unique:
            result = result.unique()
        if fetch == "all":
            rows = result.all()
        else:
            item = result.one_or_none()
            rows = [] if item is None else [item]
        for row in rows:
            (obj, *computed_values) = row
            (_, *computed_fields) = row._fields
            nodes.append(obj)
            computed.append(dict(zip(computed_fields, computed_values, strict=True)))

        root_aggregations_set = {function.name for function in self.root_aggregation_functions}
        first_computed = computed[0] if computed else {}
        query_computed_values = {name: value for name, value in first_computed.items() if name in root_aggregations_set}

        return QueryResult(
            nodes=nodes,
            node_computed_values=computed,
            query_computed_values=defaultdict(lambda: None) | query_computed_values,
            node_key=self.scope.key,
        )

    def statement(self) -> Select[tuple[DeclarativeT]] | StatementLambdaElement:
        """Returns the SQLAlchemy statement to be executed.

        Returns:
            The SQLAlchemy statement.
        """
        statement = self.base_statement
        if self.execution_options:
            statement = statement.execution_options(**self.execution_options)
        return statement


@dataclass
class AsyncQueryExecutor(QueryExecutor[DeclarativeT]):
    async def execute(self, session: AnyAsyncSession) -> Result[tuple[DeclarativeT, Any]]:
        """Executes the given SQLAlchemy statement.

        Args:
            session: The SQLAlchemy AnyAsyncSession to use.
            statement: The SQLAlchemy statement to execute. If None, the
                base statement is used.

        Returns:
            The result of the execution.
        """
        return await session.execute(self.statement())

    async def list(self, session: AnyAsyncSession) -> QueryResult[DeclarativeT]:
        """Executes the statement and returns a QueryResult object containing all results.

        Args:
            session: The SQLAlchemy AnyAsyncSession to use.
            statement: The SQLAlchemy statement to execute. If None, the
                base statement is used.

        Returns:
            A QueryResult object containing all results.
        """
        return self._to_query_result(await self.execute(session), "all")

    async def get_one_or_none(self, session: AnyAsyncSession) -> QueryResult[DeclarativeT]:
        """Executes the statement and returns a QueryResult object containing at most one result.

        Args:
            session: The SQLAlchemy AnyAsyncSession to use.
            statement: The SQLAlchemy statement to execute. If None, the
                base statement is used.

        Returns:
            A QueryResult object containing at most one result.
        """
        return self._to_query_result(await self.execute(session), "one_or_none")


@dataclass
class SyncQueryExecutor(QueryExecutor[DeclarativeT]):
    def execute(self, session: AnySyncSession) -> Result[tuple[DeclarativeT, Any]]:
        """Executes the given SQLAlchemy statement.

        Args:
            session: The SQLAlchemy AnySyncSession to use.
            statement: The SQLAlchemy statement to execute. If None, the
                base statement is used.

        Returns:
            The result of the execution.
        """
        return session.execute(self.statement())

    def list(self, session: AnySyncSession) -> QueryResult[DeclarativeT]:
        """Executes the statement and returns a QueryResult object containing all results.

        Args:
            session: The SQLAlchemy AnySyncSession to use.
            statement: The SQLAlchemy statement to execute. If None, the
                base statement is used.

        Returns:
            A QueryResult object containing all results.
        """
        return self._to_query_result(self.execute(session), "all")

    def get_one_or_none(self, session: AnySyncSession) -> QueryResult[DeclarativeT]:
        """Executes the statement and returns a QueryResult object containing at most one result.

        Args:
            session: The SQLAlchemy AnySyncSession to use.
            statement: The SQLAlchemy statement to execute. If None, the
                base statement is used.

        Returns:
            A QueryResult object containing at most one result.
        """
        return self._to_query_result(self.execute(session), "one_or_none")
