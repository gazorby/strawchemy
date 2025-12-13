"""Module for executing SQLAlchemy queries and converting results to QueryResult.

This module defines the QueryExecutor class, which provides methods for
executing SQLAlchemy queries and converting the results into QueryResult
objects.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal

from typing_extensions import Self

from strawchemy.dto import ModelT

from .exceptions import QueryResultError
from .typing import AnyAsyncSession, AnySyncSession, DeclarativeT

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Sequence

    from sqlalchemy import Label, Result, Select, StatementLambdaElement
    from strawchemy.strawberry.typing import QueryNodeType

    from ._scope import QueryScope


__all__ = ("AsyncQueryExecutor", "NodeResult", "QueryExecutor", "SyncQueryExecutor")


@dataclass
class NodeResult(Generic[ModelT]):
    """Represents a single node result from a query.

    Attributes:
        model: The SQLAlchemy model instance.
        computed_values: A dictionary of computed values for this node.
        node_key: A callable to generate a key for a query node type.
    """

    model: ModelT
    computed_values: dict[str, Any]
    node_key: Callable[[QueryNodeType], str]

    def value(self, key: QueryNodeType) -> Any:
        """Retrieves the value for a given query node type.

        If the key represents a computed or transformed value, it's fetched
        from `computed_values`. Otherwise, it's retrieved as an attribute
        from the `model`.

        Args:
            key: The query node type representing the desired value.

        Returns:
            The value corresponding to the key.
        """
        if key.value.is_computed or key.metadata.data.is_transform:
            return self.computed_values[self.node_key(key)]
        return getattr(self.model, key.value.model_field_name)

    def copy_with(self, model: Any) -> Self:
        """Creates a copy of this NodeResult with a new model.

        Args:
            model: The new model instance to use.

        Returns:
            A new NodeResult instance with the updated model.
        """
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

    node_key: Callable[[QueryNodeType], str] = lambda key: str(key)
    nodes: Sequence[ModelT] = dataclasses.field(default_factory=list)
    node_computed_values: Sequence[dict[str, Any]] = dataclasses.field(default_factory=list)
    query_computed_values: defaultdict[str, Any] = dataclasses.field(default_factory=lambda: defaultdict(lambda: None))

    def __post_init__(self) -> None:
        if not self.node_computed_values:
            self.node_computed_values = [{} for _ in range(len(self.nodes))]

    def __iter__(self) -> Generator[NodeResult[ModelT]]:
        """Iterates over the query results, yielding NodeResult instances.

        Yields:
            NodeResult[ModelT]: An individual result node.
        """
        for model, computed_values in zip(self.nodes, self.node_computed_values):
            yield NodeResult(model, computed_values, self.node_key)

    def filter_in(self, **kwargs: Sequence[Any]) -> Self:
        """Filters the query results based on attribute values.

        Keeps only the nodes where the specified attributes are present in the
        provided sequences of values.

        Args:
            **kwargs: Keyword arguments where keys are attribute names of the
                model and values are sequences of allowed values for that attribute.

        Returns:
            A new QueryResult instance with the filtered nodes.
        """
        filtered = [
            (model, computed_values)
            for model, computed_values in zip(self.nodes, self.node_computed_values)
            if all(getattr(model, key) in value for key, value in kwargs.items())
        ]
        nodes, computed_values = list(map(list, zip(*filtered))) if filtered else ([], [])
        return dataclasses.replace(self, nodes=nodes, node_computed_values=computed_values)

    def value(self, key: QueryNodeType) -> Any:
        """Retrieves a query-level computed value.

        Args:
            key: The query node type representing the desired query-level
                computed value.

        Returns:
            The computed value for the query.
        """
        return self.query_computed_values[self.node_key(key)]

    def one(self) -> NodeResult[ModelT]:
        """Returns the single result node.

        Raises:
            QueryResultError: If the number of nodes is not exactly one.

        Returns:
            The single NodeResult.
        """
        if len(self.nodes) != 1 or len(self.node_computed_values) != 1:
            msg = f"Expected one item, got {len(self.nodes)}"
            raise QueryResultError(msg)
        return NodeResult(self.nodes[0], self.node_computed_values[0], self.node_key)

    def one_or_none(self) -> NodeResult[ModelT] | None:
        """Returns the single result node, or None if there isn't exactly one result.

        Returns:
            The single NodeResult or None.
        """
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
            computed.append(dict(zip(computed_fields, computed_values)))

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
    """Extends QueryExecutor to provide asynchronous query execution.

    This class inherits the query building capabilities of `QueryExecutor`
    and adapts them for an asynchronous environment. It uses an `AnyAsyncSession`
    to execute the SQLAlchemy statements and retrieve results.

    The primary methods `execute`, `list`, and `get_one_or_none` are implemented
    as asynchronous methods, suitable for use with `async/await`.
    """

    async def execute(self, session: AnyAsyncSession) -> Result[tuple[DeclarativeT, Any]]:
        """Executes the SQLAlchemy statement.

        The statement to be executed is determined by the `self.statement()`
        method.

        Args:
            session: The SQLAlchemy AnyAsyncSession to use.

        Returns:
            The result of the execution.
        """
        return await session.execute(self.statement())

    async def list(self, session: AnyAsyncSession) -> QueryResult[DeclarativeT]:
        """Executes the statement and returns a QueryResult object containing all results.

        The statement to be executed is determined by the `self.statement()`
        method.

        Args:
            session: The SQLAlchemy AnyAsyncSession to use.

        Returns:
            A QueryResult object containing all results.
        """
        return self._to_query_result(await self.execute(session), "all")

    async def get_one_or_none(self, session: AnyAsyncSession) -> QueryResult[DeclarativeT]:
        """Executes the statement and returns a QueryResult object containing at most one result.

        The statement to be executed is determined by the `self.statement()`
        method.

        Args:
            session: The SQLAlchemy AnyAsyncSession to use.

        Returns:
            A QueryResult object containing at most one result.
        """
        return self._to_query_result(await self.execute(session), "one_or_none")


@dataclass
class SyncQueryExecutor(QueryExecutor[DeclarativeT]):
    """Extends QueryExecutor to provide synchronous query execution.

    This class inherits the query building capabilities of `QueryExecutor`
    and adapts them for a synchronous environment. It uses an `AnySyncSession`
    to execute the SQLAlchemy statements and retrieve results.

    The primary methods `execute`, `list`, and `get_one_or_none` are implemented
    as synchronous methods.
    """

    def execute(self, session: AnySyncSession) -> Result[tuple[DeclarativeT, Any]]:
        """Executes the SQLAlchemy statement.

        The statement to be executed is determined by the `self.statement()`
        method.

        Args:
            session: The SQLAlchemy AnySyncSession to use.

        Returns:
            The result of the execution.
        """
        return session.execute(self.statement())

    def list(self, session: AnySyncSession) -> QueryResult[DeclarativeT]:
        """Executes the statement and returns a QueryResult object containing all results.

        The statement to be executed is determined by the `self.statement()`
        method.

        Args:
            session: The SQLAlchemy AnySyncSession to use.

        Returns:
            A QueryResult object containing all results.
        """
        return self._to_query_result(self.execute(session), "all")

    def get_one_or_none(self, session: AnySyncSession) -> QueryResult[DeclarativeT]:
        """Executes the statement and returns a QueryResult object containing at most one result.

        The statement to be executed is determined by the `self.statement()`
        method.

        Args:
            session: The SQLAlchemy AnySyncSession to use.

        Returns:
            A QueryResult object containing at most one result.
        """
        return self._to_query_result(self.execute(session), "one_or_none")
