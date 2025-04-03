from __future__ import annotations

from collections import defaultdict, namedtuple
from typing import TYPE_CHECKING, Any, NamedTuple, TypeAlias, TypeVar

from sqlalchemy import Row, insert, update
from sqlalchemy.orm import RelationshipProperty
from strawchemy.graphql.mutation import InputData, LevelInput, RelationType
from strawchemy.sqlalchemy._executor import AsyncQueryExecutor, QueryResult
from strawchemy.sqlalchemy.typing import AnyAsyncSession, DeclarativeT, SQLAlchemyQueryNode

from ._base import SQLAlchemyGraphQLRepository

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
    from strawchemy.graphql.dto import BooleanFilterDTO, EnumDTO, OrderByDTO
    from strawchemy.sqlalchemy.hook import QueryHook


__all__ = ("SQLAlchemyGraphQLAsyncRepository",)

T = TypeVar("T", bound=Any)

RowLike: TypeAlias = "Row[Any] | NamedTuple"


class SQLAlchemyGraphQLAsyncRepository(SQLAlchemyGraphQLRepository[DeclarativeT, AnyAsyncSession]):
    async def _insert(
        self,
        model_type: type[DeclarativeBase],
        values: list[dict[str, Any]],
        level: LevelInput[DeclarativeBase, QueryableAttribute[Any]],
    ) -> None:
        results = await self.session.execute(
            insert(model_type).returning(*model_type.__mapper__.primary_key, sort_by_parameter_order=True),
            values,
        )
        instance_ids = results.all()
        pk_names = [pk.name for pk in model_type.__mapper__.primary_key]

        pk_index, fk_index = 0, 0
        for relation_input in level.inputs:
            if not isinstance(relation_input.instance, model_type):
                continue
            # Update Pks
            for column in model_type.__mapper__.primary_key:
                setattr(relation_input.instance, column.key, instance_ids[pk_index][pk_names.index(column.key)])
            pk_index += 1
            if relation_input.relation.relation_type is RelationType.TO_MANY:
                continue
            # Update Fks
            prop = relation_input.relation.field.model_field.property
            assert isinstance(prop, RelationshipProperty)
            assert prop.local_remote_pairs
            for local, remote in prop.local_remote_pairs:
                assert local.key
                assert remote.key
                setattr(relation_input.relation.parent, local.key, instance_ids[fk_index][pk_names.index(remote.key)])
            fk_index += 1

    async def _create_nested_to_one_relations(self, data: InputData[DeclarativeBase, QueryableAttribute[Any]]) -> None:
        for level in data.filter_by_level(RelationType.TO_ONE, "create"):
            insert_params: defaultdict[type[DeclarativeBase], list[dict[str, Any]]] = defaultdict(list)

            for create_input in level.inputs:
                assert create_input.relation.field.related_model
                insert_params[create_input.relation.field.related_model].append(self._to_dict(create_input.instance))

            for model_type, values in insert_params.items():
                await self._insert(model_type, values, level)

    async def _connect_to_many_relations(
        self, data: InputData[DeclarativeBase, QueryableAttribute[Any]], created_ids: Sequence[RowLike]
    ) -> None:
        for level in data.filter_by_level(RelationType.TO_MANY, "set"):
            update_params: defaultdict[type[DeclarativeBase], list[dict[str, Any]]] = defaultdict(list)
            for set_input in level.inputs:
                relation = set_input.relation
                prop = relation.field.model_field.property
                assert prop.local_remote_pairs
                assert relation.field.related_model
                parent = created_ids[relation.input_index] if relation.level == 1 else relation.parent
                update_params[relation.field.related_model].extend(
                    [
                        {
                            column.key: getattr(relation_model, column.key)
                            for column in relation_model.__mapper__.primary_key
                        }
                        | {
                            remote.key: getattr(parent, local.key)
                            for local, remote in prop.local_remote_pairs
                            if local.key and remote.key
                        }
                        for relation_model in relation.set
                    ]
                )

            for model_type, values in update_params.items():
                await self.session.execute(update(model_type), values)

    async def _create_to_many_relations(
        self, data: InputData[DeclarativeBase, QueryableAttribute[Any]], created_ids: Sequence[RowLike]
    ) -> None:
        for level in data.filter_by_level(RelationType.TO_MANY, "create"):
            insert_params: defaultdict[type[DeclarativeBase], list[dict[str, Any]]] = defaultdict(list)
            for create_input in level.inputs:
                relation = create_input.relation
                prop = relation.field.model_field.property
                assert prop.local_remote_pairs
                assert relation.field.related_model
                parent = created_ids[relation.input_index] if relation.level == 1 else relation.parent
                fks = {
                    remote.key: getattr(parent, local.key)
                    for local, remote in prop.local_remote_pairs
                    if local.key and remote.key
                }
                insert_params[relation.field.related_model].append(self._to_dict(create_input.instance) | fks)

            for model_type, values in insert_params.items():
                await self._insert(model_type, values, level)

    async def _create_many(self, data: InputData[DeclarativeBase, QueryableAttribute[Any]]) -> Sequence[RowLike]:
        async with self.session.begin_nested() as transaction:
            self._connect_to_one_relations(data)
            await self._create_nested_to_one_relations(data)
            result = await self.session.execute(
                insert(self.model).returning(*self.model.__mapper__.primary_key, sort_by_parameter_order=True),
                [self._to_dict(instance) for instance in data.input_instances],
            )
            instance_ids = result.all()
            await self._connect_to_many_relations(data, instance_ids)
            await self._create_to_many_relations(data, instance_ids)
            await transaction.commit()
        return instance_ids

    async def _update_many(self, data: InputData[DeclarativeBase, QueryableAttribute[Any]]) -> Sequence[RowLike]:
        pks = [column.key for column in self.model.__mapper__.primary_key]
        pk_tuple = namedtuple("AsRow", pks)  # pyright: ignore[reportUntypedNamedTuple]  # noqa: PYI024
        async with self.session.begin_nested() as transaction:
            self._connect_to_one_relations(data)
            await self._create_nested_to_one_relations(data)
            update_values = [self._to_dict(instance) for instance in data.input_instances]
            instance_ids = [pk_tuple(*[instance[name] for name in pks]) for instance in update_values]
            await self.session.execute(update(self.model), update_values)
            await self._connect_to_many_relations(data, instance_ids)
            await self._create_to_many_relations(data, instance_ids)
            await transaction.commit()
        return instance_ids

    async def _list_by_ids(
        self, id_rows: Sequence[RowLike], selection: SQLAlchemyQueryNode | None = None
    ) -> QueryResult[DeclarativeT]:
        executor = self._get_query_executor(AsyncQueryExecutor, selection=selection)
        id_fields = executor.scope.id_field_definitions(self.model)
        executor.base_statement = executor.base_statement.where(
            *[field.model_field.in_([getattr(row, field.model_field_name) for row in id_rows]) for field in id_fields]
        )
        return await executor.list(self.session)

    async def list(
        self,
        selection: SQLAlchemyQueryNode | None = None,
        dto_filter: BooleanFilterDTO[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        order_by: list[OrderByDTO[DeclarativeBase, QueryableAttribute[Any]]] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct_on: list[EnumDTO] | None = None,
        allow_null: bool = False,
        query_hooks: defaultdict[SQLAlchemyQueryNode, list[QueryHook[DeclarativeBase]]] | None = None,
        execution_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> QueryResult[DeclarativeT]:
        executor = self._get_query_executor(
            executor_type=AsyncQueryExecutor,
            selection=selection,
            dto_filter=dto_filter,
            order_by=order_by,
            limit=limit,
            offset=offset,
            distinct_on=distinct_on,
            allow_null=allow_null,
            query_hooks=query_hooks,
            execution_options=execution_options,
        )
        return await executor.list(self.session)

    async def get_one(
        self,
        selection: SQLAlchemyQueryNode | None = None,
        dto_filter: BooleanFilterDTO[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        order_by: list[OrderByDTO[DeclarativeBase, QueryableAttribute[Any]]] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct_on: list[EnumDTO] | None = None,
        allow_null: bool = False,
        query_hooks: defaultdict[SQLAlchemyQueryNode, list[QueryHook[DeclarativeBase]]] | None = None,
        execution_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> QueryResult[DeclarativeT]:
        executor = self._get_query_executor(
            executor_type=AsyncQueryExecutor,
            selection=selection,
            dto_filter=dto_filter,
            order_by=order_by,
            limit=limit,
            offset=offset,
            distinct_on=distinct_on,
            allow_null=allow_null,
            query_hooks=query_hooks,
            execution_options=execution_options,
            **kwargs,
        )
        return await executor.get_one_or_none(self.session)

    async def get_by_id(
        self,
        selection: SQLAlchemyQueryNode | None = None,
        query_hooks: defaultdict[SQLAlchemyQueryNode, list[QueryHook[DeclarativeBase]]] | None = None,
        execution_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> QueryResult[DeclarativeT]:
        executor = self._get_query_executor(
            AsyncQueryExecutor, selection=selection, query_hooks=query_hooks, execution_options=execution_options
        )
        executor.base_statement = executor.base_statement.where(
            *[
                field_def.model_field == kwargs.pop(field_def.name)
                for field_def in executor.scope.id_field_definitions(self.model)
            ]
        )
        return await executor.get_one_or_none(self.session)

    async def create(
        self, data: InputData[DeclarativeBase, QueryableAttribute[Any]], selection: SQLAlchemyQueryNode | None = None
    ) -> QueryResult[DeclarativeT]:
        created_ids = await self._create_many(data)
        return await self._list_by_ids(created_ids, selection)

    async def update(
        self, data: InputData[DeclarativeBase, QueryableAttribute[Any]], selection: SQLAlchemyQueryNode | None = None
    ) -> QueryResult[DeclarativeT]:
        update_ids = await self._update_many(data)
        return await self._list_by_ids(update_ids, selection)
