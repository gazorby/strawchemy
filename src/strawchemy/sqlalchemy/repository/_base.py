from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from sqlalchemy import inspect
from sqlalchemy.orm import NO_VALUE, RelationshipProperty
from strawchemy.graphql.mutation import RelationType
from strawchemy.sqlalchemy._transpiler import QueryTranspiler
from strawchemy.sqlalchemy.typing import DeclarativeT, QueryExecutorT, SessionT, SQLAlchemyQueryNode

if TYPE_CHECKING:
    from collections import defaultdict

    from sqlalchemy import Select
    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
    from strawchemy.graphql.dto import BooleanFilterDTO, EnumDTO, OrderByDTO
    from strawchemy.input import Input
    from strawchemy.sqlalchemy.hook import QueryHook


__all__ = ("SQLAlchemyGraphQLRepository",)


T = TypeVar("T", bound=Any)


class SQLAlchemyGraphQLRepository(Generic[DeclarativeT, SessionT]):
    def __init__(
        self,
        model: type[DeclarativeT],
        session: SessionT,
        statement: Select[tuple[DeclarativeT]] | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.session = session
        self.statement = statement
        self.execution_options = execution_options

        self._dialect = session.get_bind().dialect

    def _get_query_executor(
        self,
        executor_type: type[QueryExecutorT],
        selection: SQLAlchemyQueryNode | None = None,
        dto_filter: BooleanFilterDTO[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        order_by: list[OrderByDTO[DeclarativeBase, QueryableAttribute[Any]]] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct_on: list[EnumDTO] | None = None,
        allow_null: bool = False,
        query_hooks: defaultdict[SQLAlchemyQueryNode, list[QueryHook[DeclarativeBase]]] | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> QueryExecutorT:
        transpiler = QueryTranspiler(self.model, self._dialect, query_hooks=query_hooks, statement=self.statement)
        return transpiler.select_executor(
            selection_tree=selection,
            dto_filter=dto_filter,
            order_by=order_by,
            limit=limit,
            offset=offset,
            distinct_on=distinct_on,
            allow_null=allow_null,
            executor_cls=executor_type,
            execution_options=execution_options if execution_options is not None else self.execution_options,
        )

    @classmethod
    def _loaded_attributes(cls, model: DeclarativeBase) -> set[str]:
        return {name for name, attr in inspect(model).attrs.items() if attr.loaded_value is not NO_VALUE}

    def _to_dict(self, model: DeclarativeBase) -> dict[str, Any]:
        return {
            field: getattr(model, field)
            for field in model.__mapper__.columns.keys()  # noqa: SIM118
            if field in self._loaded_attributes(model)
        }

    def _connect_to_one_relations(self, data: Input[DeclarativeT]) -> None:
        for relation in data.relations:
            prop = relation.attribute
            if (
                (not relation.set and relation.set is not None)
                or not isinstance(prop, RelationshipProperty)
                or relation.relation_type is not RelationType.TO_ONE
            ):
                continue
            assert prop.local_remote_pairs
            for local, remote in prop.local_remote_pairs:
                assert local.key
                assert remote.key
                # We take the first input as it's a *ToOne relation
                value = getattr(relation.set[0], remote.key) if relation.set else None
                setattr(relation.parent, local.key, value)
