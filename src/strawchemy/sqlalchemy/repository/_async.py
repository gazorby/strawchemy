from __future__ import annotations

from collections import defaultdict, namedtuple
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, TypeAlias, TypeVar

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
    async def _insert_nested(
        self,
        model_type: type[DeclarativeBase],
        values: list[dict[str, Any]],
        level: LevelInput[DeclarativeBase, QueryableAttribute[Any]],
    ) -> None:
        """Inserts multiple records for a given model type and updates related instances.

        This internal method performs a bulk insert operation for the specified
        SQLAlchemy model type using the provided values. After insertion, it
        retrieves the primary keys of the newly created records and updates
        the corresponding instance objects within the provided `level` input
        with these keys. It also handles updating foreign keys for to-one
        relationships where applicable.

        Args:
            model_type: The SQLAlchemy declarative base class to insert records for.
            values: A list of dictionaries, where each dictionary represents the
                data for a single record to be inserted.
            level: The input level containing information about the instances being
                created and their relationships, used to update instances with
                generated primary and foreign keys.
        """
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
        """Creates nested related objects for to-one relationships.

        Iterates through the input data levels filtered for 'create' operations
        on to-one relationships. It groups the instances to be created by their
        model type and then calls `_insert` for each type to perform bulk
        insertions.

        Args:
            data: The processed input data containing nested structures and
                relationship information.
        """
        for level in data.filter_by_level(RelationType.TO_ONE, "create"):
            insert_params: defaultdict[type[DeclarativeBase], list[dict[str, Any]]] = defaultdict(list)

            for create_input in level.inputs:
                assert create_input.relation.field.related_model
                insert_params[create_input.relation.field.related_model].append(self._to_dict(create_input.instance))

            for model_type, values in insert_params.items():
                await self._insert_nested(model_type, values, level)

    async def _connect_to_many_relations(
        self, data: InputData[DeclarativeBase, QueryableAttribute[Any]], created_ids: Sequence[RowLike]
    ) -> None:
        """Updates foreign keys to connect existing related objects for to-many relationships.

        Iterates through the input data levels filtered for 'set' operations
        on to-many relationships. For each relationship, it prepares bulk update
        statements to set the foreign keys on the related models, linking them
        to the parent objects (either newly created or existing).

        Args:
            data: The processed input data containing relationship information.
            created_ids: A sequence of RowLike objects containing the primary keys
                of the main objects created or updated in the parent operation.
                Used to link the 'set' relations to the correct parent.
        """
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
        """Creates and connects new related objects for to-many relationships.

        Iterates through the input data levels filtered for 'create' operations
        on to-many relationships. It prepares the data for the new related
        objects, including setting the foreign keys based on the parent object's
        primary key, and then calls `_insert` to perform bulk insertions.

        Args:
            data: The processed input data containing nested structures and
                relationship information.
            created_ids: A sequence of RowLike objects containing the primary keys
                of the main objects created in the parent operation. Used to set
                foreign keys on the newly created related objects.
        """
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
                await self._insert_nested(model_type, values, level)

    async def _mutate(
        self, mode: Literal["insert", "update"], data: InputData[DeclarativeBase, QueryableAttribute[Any]]
    ) -> Sequence[RowLike]:
        model_pks = self.model.__mapper__.primary_key
        async with self.session.begin_nested() as transaction:
            self._connect_to_one_relations(data)
            await self._create_nested_to_one_relations(data)
            values = [self._to_dict(instance) for instance in data.input_instances]
            if mode == "insert":
                result = await self.session.execute(
                    insert(self.model).returning(*model_pks, sort_by_parameter_order=True), values
                )
                instance_ids = result.all()
            else:
                pks = [column.key for column in model_pks]
                pk_tuple = namedtuple("AsRow", pks)  # pyright: ignore[reportUntypedNamedTuple]  # noqa: PYI024
                await self.session.execute(update(self.model), values)
                instance_ids = [pk_tuple(*[instance[name] for name in pks]) for instance in values]
            await self._create_to_many_relations(data, instance_ids)
            await self._connect_to_many_relations(data, instance_ids)
            await transaction.commit()
        return instance_ids

    async def _list_by_ids(
        self, id_rows: Sequence[RowLike], selection: SQLAlchemyQueryNode | None = None
    ) -> QueryResult[DeclarativeT]:
        """Retrieves multiple records by their primary keys with optional selection.

        Fetches records from the repository's main model that match the provided
        primary key combinations. Allows specifying a GraphQL selection

        Args:
            id_rows: A sequence of RowLike objects, each containing the primary
                key values for one record to retrieve.
            selection: An optional SQLAlchemyQueryNode representing the GraphQL
                selection set to apply to the query.

        Returns:
            A QueryResult containing the list of fetched records matching the
            provided IDs, structured according to the selection.
        """
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
        """Retrieves a list of records based on filtering, ordering, and pagination.

        Fetches records from the repository's main model, applying optional
        filtering, ordering, pagination (limit/offset), and distinct constraints.
        Supports GraphQL selection sets for optimized data retrieval and query hooks
        for customization.

        Args:
            selection: An optional SQLAlchemyQueryNode representing the GraphQL
                selection set.
            dto_filter: An optional filter object derived from GraphQL input.
            order_by: An optional list of ordering criteria.
            limit: An optional integer limiting the number of results.
            offset: An optional integer specifying the starting point for results.
            distinct_on: An optional list of fields for DISTINCT ON clause (if supported).
            allow_null: If True, allows certain operations even if parts of the
                filter path are null (implementation specific to executor).
            query_hooks: Optional hooks to modify the query at different stages.
            execution_options: Optional dictionary of execution options passed to
                SQLAlchemy.
            **kwargs: Additional keyword arguments (currently unused but allows extension).

        Returns:
            A QueryResult containing the list of fetched records and potentially
            pagination info or total count, structured according to the selection.
        """
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
        """Retrieves a single record based on filtering and ordering criteria.

        Fetches a single record matching the provided filters. If multiple records
        match, ordering, limit, and offset can be used to pinpoint one. Returns
        None if no record matches. Supports GraphQL selection sets and query hooks.

        Args:
            selection: An optional SQLAlchemyQueryNode representing the GraphQL
                selection set.
            dto_filter: An optional filter object derived from GraphQL input.
            order_by: An optional list of ordering criteria.
            limit: An optional integer limiting the number of potential matches
                considered (usually 1 for get_one).
            offset: An optional integer specifying the starting point.
            distinct_on: An optional list of fields for DISTINCT ON clause.
            allow_null: If True, allows certain operations even if parts of the
                filter path are null.
            query_hooks: Optional hooks to modify the query.
            execution_options: Optional dictionary of execution options.
            **kwargs: Additional keyword arguments passed to the query executor setup.

        Returns:
            A QueryResult containing the single fetched record or None, structured
            according to the selection.
        """
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
        """Retrieves a single record by its primary key(s).

        Fetches a single record matching the provided primary key values passed
        as keyword arguments. Returns None if no record matches. Supports GraphQL
        selection sets and query hooks.

        Args:
            selection: An optional SQLAlchemyQueryNode representing the GraphQL
                selection set.
            query_hooks: Optional hooks to modify the query.
            execution_options: Optional dictionary of execution options.
            **kwargs: Keyword arguments where keys are the primary key field names
                and values are the corresponding primary key values.

        Returns:
            A QueryResult containing the single fetched record or None, structured
            according to the selection.
        """
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
        """Creates one or more records with nested relationships and returns them.

        Takes processed input data, performs the creation using `_create_many`,
        and then fetches the newly created records using `_list_by_ids` based on
        the returned primary keys and the provided selection set.

        Args:
            data: The processed input data for creation.
            selection: An optional SQLAlchemyQueryNode representing the GraphQL
                selection set for the returned data.

        Returns:
            A QueryResult containing the newly created records, structured
            according to the selection.
        """
        created_ids = await self._mutate("insert", data)
        return await self._list_by_ids(created_ids, selection)

    async def update(
        self, data: InputData[DeclarativeBase, QueryableAttribute[Any]], selection: SQLAlchemyQueryNode | None = None
    ) -> QueryResult[DeclarativeT]:
        """Updates one or more records with nested relationships and returns them.

        Takes processed input data, performs the update using `_update_many`,
        and then fetches the updated records using `_list_by_ids` based on
        the returned primary keys and the provided selection set.

        Args:
            data: The processed input data for update. Must include primary keys.
            selection: An optional SQLAlchemyQueryNode representing the GraphQL
                selection set for the returned data.

        Returns:
            A QueryResult containing the updated records, structured
            according to the selection.
        """
        updated_ids = await self._mutate("update", data)
        return await self._list_by_ids(updated_ids, selection)
