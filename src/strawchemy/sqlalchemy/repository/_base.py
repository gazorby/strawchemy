from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeAlias, TypeVar

from sqlalchemy import Column, Function, Insert, Row, func, insert
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.orm import RelationshipProperty
from strawchemy.dto.inspectors.sqlalchemy import SQLAlchemyInspector
from strawchemy.exceptions import StrawchemyError
from strawchemy.sqlalchemy._transpiler import QueryTranspiler
from strawchemy.sqlalchemy.typing import DeclarativeT, QueryExecutorT, SessionT
from strawchemy.strawberry.mutation.types import RelationType

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy import Select
    from sqlalchemy.orm import DeclarativeBase
    from sqlalchemy.sql.base import ReadOnlyColumnCollection
    from sqlalchemy.sql.elements import KeyedColumnElement
    from strawchemy.sqlalchemy.hook import QueryHook
    from strawchemy.strawberry.dto import BooleanFilterDTO, EnumDTO, OrderByDTO
    from strawchemy.strawberry.mutation.input import Input, UpsertData
    from strawchemy.strawberry.typing import QueryNodeType
    from strawchemy.typing import SupportedDialect


__all__ = ("SQLAlchemyGraphQLRepository",)


T = TypeVar("T", bound=Any)
InsertOrUpdate: TypeAlias = Literal["insert", "update_by_pks", "update_where", "upsert"]


@dataclass(frozen=True)
class InsertData:
    model_type: type[DeclarativeBase]
    values: list[dict[str, Any]]
    upsert_data: UpsertData | None = None

    @property
    def is_upsert(self) -> bool:
        return self.upsert_data is not None

    @property
    def upsert_data_or_raise(self) -> UpsertData:
        if self.upsert_data is None:
            msg = "UpsertData is required"
            raise StrawchemyError(msg)
        return self.upsert_data

    def conflict_target_columns(self) -> list[Column[Any]]:
        if self.upsert_data_or_raise.conflict_constraint:
            return list(self.upsert_data_or_raise.conflict_constraint.value.columns)
        return list(self.model_type.__mapper__.primary_key)

    def upsert_set(
        self, dialect: SupportedDialect, columns: ReadOnlyColumnCollection[str, KeyedColumnElement[Any]]
    ) -> Mapping[Column[Any], KeyedColumnElement[Any] | Function[Any]]:
        update_fields_set = {
            dto_field.field_definition.model_field_name for dto_field in self.upsert_data_or_raise.update_fields
        } or {name for value_dict in self.values for name in value_dict}
        mapper = self.model_type.__mapper__
        update_fields = {mapper.columns[name]: value for name, value in columns.items() if name in update_fields_set}
        if (
            dialect == "mysql"
            and (
                auto_increment_pk_column := next(
                    (column for column in self.model_type.__mapper__.primary_key if column.autoincrement),
                    None,
                )
            )
            is not None
        ):
            update_fields = {auto_increment_pk_column: func.last_insert_id(auto_increment_pk_column)} | update_fields
        return update_fields


@dataclass(frozen=True)
class MutationData(Generic[DeclarativeT]):
    mode: InsertOrUpdate
    input: Input[DeclarativeT]
    dto_filter: BooleanFilterDTO | None = None
    upsert_update_fields: list[EnumDTO] | None = None
    upsert_conflict_fields: EnumDTO | None = None


class SQLAlchemyGraphQLRepository(Generic[DeclarativeT, SessionT]):
    def __init__(
        self,
        model: type[DeclarativeT],
        session: SessionT,
        statement: Select[tuple[DeclarativeT]] | None = None,
        execution_options: dict[str, Any] | None = None,
        deterministic_ordering: bool = False,
    ) -> None:
        self.model = model
        self.session = session
        self.statement = statement
        self.execution_options = execution_options
        self.deterministic_ordering = deterministic_ordering

        self._dialect = session.get_bind().dialect

    def _get_query_executor(
        self,
        executor_type: type[QueryExecutorT],
        selection: QueryNodeType | None = None,
        dto_filter: BooleanFilterDTO | None = None,
        order_by: list[OrderByDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct_on: list[EnumDTO] | None = None,
        allow_null: bool = False,
        query_hooks: defaultdict[QueryNodeType, list[QueryHook[DeclarativeBase]]] | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> QueryExecutorT:
        transpiler = QueryTranspiler(
            self.model,
            self._dialect,
            query_hooks=query_hooks,
            statement=self.statement,
            deterministic_ordering=self.deterministic_ordering,
        )
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

    def _insert_statement(self, data: InsertData) -> Insert:
        if not data.is_upsert:
            return insert(data.model_type)
        if self._dialect.name == "postgresql":
            statement = postgresql.insert(data.model_type)
            statement = statement.on_conflict_do_update(
                set_=data.upsert_set(self._dialect.name, statement.excluded),
                index_elements=data.conflict_target_columns(),
            )
        elif self._dialect.name == "sqlite":
            statement = sqlite.insert(data.model_type)
            statement = statement.on_conflict_do_update(
                set_=data.upsert_set(self._dialect.name, statement.excluded),
                index_elements=data.conflict_target_columns(),
            )
        elif self._dialect.name == "mysql":
            statement = mysql.insert(data.model_type)
            statement = statement.on_duplicate_key_update(data.upsert_set(self._dialect.name, statement.inserted))
        else:
            msg = f"This dialect does not support upsert statements: {self._dialect.name}"
            raise StrawchemyError(msg)
        return statement

    def _to_dict(self, model: DeclarativeBase) -> dict[str, Any]:
        return {
            field: getattr(model, field)
            for field in model.__mapper__.columns.keys()  # noqa: SIM118
            if field in SQLAlchemyInspector.loaded_attributes(model)
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

    def _rows_to_filter_dict(self, rows: Sequence[Row[Any]]) -> dict[str, list[Any]]:
        filter_dict = defaultdict(list)
        for row in rows:
            for key, value in row._asdict().items():
                filter_dict[key].append(value)
        return filter_dict
