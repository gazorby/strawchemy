from __future__ import annotations

import dataclasses
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, NamedTuple, TypeAlias, TypeVar, Union, cast

from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.orm import RelationshipProperty

from sqlalchemy import Column, Function, Insert, Row, Table, func, insert, inspect
from strawchemy.dto.inspectors.sqlalchemy import SQLAlchemyInspector
from strawchemy.exceptions import StrawchemyError
from strawchemy.sqlalchemy._transpiler import QueryTranspiler
from strawchemy.sqlalchemy.typing import DeclarativeT, QueryExecutorT, SessionT
from strawchemy.strawberry.mutation.types import RelationType

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy.orm import DeclarativeBase
    from sqlalchemy.sql.base import ReadOnlyColumnCollection
    from sqlalchemy.sql.elements import KeyedColumnElement

    from sqlalchemy import Select
    from strawchemy.sqlalchemy.hook import QueryHook
    from strawchemy.strawberry.dto import BooleanFilterDTO, EnumDTO, OrderByDTO
    from strawchemy.strawberry.mutation.input import Input, LevelInput, UpsertData
    from strawchemy.strawberry.typing import QueryNodeType
    from strawchemy.typing import SupportedDialect


__all__ = ("InsertOrUpdate", "RowLike", "SQLAlchemyGraphQLRepository")


T = TypeVar("T", bound=Any)

InsertOrUpdate: TypeAlias = Literal["insert", "update_by_pks", "update_where", "upsert"]
RowLike: TypeAlias = "Row[Any] | NamedTuple"
_ModelOrTable: TypeAlias = "Union[type[DeclarativeBase], Table]"


@dataclass
class QueryParams:
    insert: defaultdict[type[DeclarativeBase], list[dict[str, Any]]] = dataclasses.field(
        default_factory=lambda: defaultdict(list)
    )
    update: defaultdict[type[DeclarativeBase], list[dict[str, Any]]] = dataclasses.field(
        default_factory=lambda: defaultdict(list)
    )
    insert_m2m: defaultdict[_ModelOrTable, list[dict[str, Any]]] = dataclasses.field(
        default_factory=lambda: defaultdict(list)
    )
    delete: defaultdict[_ModelOrTable, defaultdict[str, list[Any]]] = dataclasses.field(
        default_factory=lambda: defaultdict(lambda: defaultdict(list))
    )
    delete_m2m: defaultdict[_ModelOrTable, defaultdict[str, list[Any]]] = dataclasses.field(
        default_factory=lambda: defaultdict(lambda: defaultdict(list))
    )
    upsert_data_map: dict[type[DeclarativeBase], UpsertData] = dataclasses.field(default_factory=dict)


@dataclass(frozen=True)
class InsertData:
    model_type: type[DeclarativeBase] | Table
    values: list[dict[str, Any]]
    upsert_data: UpsertData | None = None

    @property
    def pks(self) -> tuple[Column[Any], ...]:
        return inspect(self.model_type, raiseerr=True).primary_key

    @property
    def _columns(self) -> Mapping[str, Column[Any]]:
        return inspect(self.model_type, raiseerr=True).columns

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
        return list(self.pks)

    def upsert_set(
        self, dialect: SupportedDialect, columns: ReadOnlyColumnCollection[str, KeyedColumnElement[Any]]
    ) -> Mapping[Column[Any], KeyedColumnElement[Any] | Function[Any]]:
        update_fields_set = {
            dto_field.field_definition.model_field_name for dto_field in self.upsert_data_or_raise.update_fields
        } or {name for value_dict in self.values for name in value_dict}
        update_fields = {self._columns[name]: value for name, value in columns.items() if name in update_fields_set}
        if (
            dialect == "mysql"
            and (
                auto_increment_pk_column := next(
                    (column for column in self.pks if column.autoincrement),
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

    def _m2m_values(
        self, model: DeclarativeBase, parent: RowLike | DeclarativeBase, relationship: RelationshipProperty[Any]
    ) -> dict[str, Any]:
        assert relationship.local_remote_pairs
        return {
            remote.key: getattr(model, local.key) if local.table is model.__table__ else getattr(parent, local.key)
            for local, remote in relationship.local_remote_pairs
            if local.key and remote.key
        }

    def _update_values(
        self, model: DeclarativeBase, parent: RowLike | DeclarativeBase, relationship: RelationshipProperty[Any]
    ) -> dict[str, Any]:
        assert relationship.local_remote_pairs
        if relationship.secondary is None:
            return {column.key: getattr(model, column.key) for column in model.__mapper__.primary_key if column.key} | {
                remote.key: getattr(parent, local.key)
                for local, remote in relationship.local_remote_pairs
                if local.key and remote.key
            }
        return self._m2m_values(model, parent, relationship)

    def _to_one_nested_create_params(self, level: LevelInput) -> QueryParams:
        params = QueryParams()

        for create_input in level.inputs:
            params.insert[create_input.relation.related].append(self._to_dict(create_input.instance))
            if create_input.relation.upsert is not None:
                params.upsert_data_map[create_input.relation.related] = create_input.relation.upsert

        return params

    def _to_many_set_params(
        self, level: LevelInput, mode: InsertOrUpdate, mutated_ids: Sequence[RowLike]
    ) -> QueryParams:
        params = QueryParams()

        for level_input in level.inputs:
            relation = level_input.relation
            prop = cast("RelationshipProperty[Any]", relation.attribute)
            assert prop.local_remote_pairs
            parent = mutated_ids[relation.input_index] if relation.level == 1 else relation.parent
            if relation.level == 1 and mode in {"update_by_pks", "update_where"}:
                for local, remote in prop.local_remote_pairs:
                    if not local.key or not remote.key:
                        continue
                    if prop.secondary is None:
                        params.delete[relation.related][remote.key].append(getattr(parent, local.key))
                    elif local.table is not relation.related.__table__:
                        params.delete_m2m[cast("Table", prop.secondary)][remote.key].append(getattr(parent, local.key))
            for relation_model in relation.set or []:
                values = self._update_values(relation_model, parent, prop)
                if prop.secondary is None:
                    params.insert[relation.related].append(values)
                else:
                    params.insert_m2m[cast("Table", prop.secondary)].append(values)

        return params

    def _to_many_update_params(self, level: LevelInput, mutated_ids: Sequence[RowLike]) -> QueryParams:
        params = QueryParams()

        for level_input in level.inputs:
            relation = level_input.relation
            prop = cast("RelationshipProperty[Any]", relation.attribute)
            assert prop.local_remote_pairs
            parent = mutated_ids[relation.input_index] if relation.level == 1 else relation.parent
            params.update[relation.related].extend(
                [self._update_values(relation_model, parent, prop) for relation_model in relation.add]
            )
            params.update[relation.related].extend(
                [
                    {
                        column.key: getattr(relation_model, column.key)
                        for column in relation_model.__mapper__.primary_key
                        if column.key
                    }
                    | {remote.key: None for local, remote in prop.local_remote_pairs if local.key and remote.key}
                    for relation_model in relation.remove
                ]
            )

        return params

    def _to_many_create_params(self, level: LevelInput, mutated_ids: Sequence[RowLike]) -> QueryParams:
        params = QueryParams()

        for create_input in level.inputs:
            relation = create_input.relation
            prop = cast("RelationshipProperty[Any]", relation.attribute)
            assert prop.local_remote_pairs
            parent = mutated_ids[relation.input_index] if relation.level == 1 else relation.parent
            fks: dict[str, Any] = {}
            if prop.secondary is None:
                fks = {
                    remote.key: getattr(parent, local.key)
                    for local, remote in prop.local_remote_pairs
                    if local.key and remote.key
                }
            params.insert[relation.related].append(self._to_dict(create_input.instance) | fks)

            if create_input.relation.upsert is not None:
                params.upsert_data_map[create_input.relation.related] = create_input.relation.upsert

        return params

    def _m2m_create_params(self, level: LevelInput, mutated_ids: Sequence[RowLike]) -> QueryParams:
        params = QueryParams()

        for create_input in level.inputs:
            relation = create_input.relation
            prop = cast("RelationshipProperty[Any]", relation.attribute)
            assert prop.local_remote_pairs
            parent = mutated_ids[relation.input_index] if relation.level == 1 else relation.parent
            if prop.secondary is not None:
                params.insert_m2m[cast("Table", prop.secondary)].append(
                    self._m2m_values(create_input.instance, parent, prop)
                )

        return params
