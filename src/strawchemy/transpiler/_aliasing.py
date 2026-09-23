"""Maps query nodes to the SQLAlchemy aliases and columns they use in the generated SQL."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeAlias

from sqlalchemy import ColumnElement, FromClause, Function, Label, Select, func, inspect
from sqlalchemy import cast as sqla_cast
from sqlalchemy import distinct as sqla_distinct
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapper, MapperProperty, QueryableAttribute, RelationshipProperty, aliased
from sqlalchemy.sql.elements import _anonymous_label
from typing_extensions import Self, override

from strawchemy.constants import NODES_KEY
from strawchemy.dto.inspectors import SQLAlchemyInspector
from strawchemy.dto.strawberry import GraphQLFieldDefinition, QueryNode
from strawchemy.dto.types import DTOConfig, Purpose
from strawchemy.exceptions import TranspilingError
from strawchemy.repository.typing import DeclarativeT

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql.elements import KeyedColumnElement

    from strawchemy.repository.typing import DeclarativeSubT, FunctionGenerator, RelationshipSide
    from strawchemy.typing import QueryNodeType, SupportedDialect

__all__ = ("AliasContext",)

_FunctionVisitor: TypeAlias = "Callable[[Function[Any]], ColumnElement[Any]]"


def require_corresponding_column(selectable: FromClause, label: KeyedColumnElement[Any]) -> KeyedColumnElement[Any]:
    """Finds the column of ``selectable`` that exposes ``label``, matched by object rather than by name.

    The column is not labelled again: a label on an anonymous column gets a name that changes between runs, and the
    executor reads values by column object anyway.

    Raises:
        TranspilingError: If ``selectable`` does not expose ``label``.
    """
    column = selectable.corresponding_column(label)
    if column is None:
        msg = f"aggregation re-projection: column {label!r} not exported by {selectable!r}"
        raise TranspilingError(msg)
    return column


def same_column(left: ColumnElement[Any], right: ColumnElement[Any]) -> bool:
    """Tells whether two selected columns are the same expression.

    ``compare()`` ignores the generated name of an anonymous label, so all ``label(None)`` columns of a LATERAL or
    CTE compare equal to each other; those are compared by object instead.
    """
    if left is right:
        return True
    if any(isinstance(getattr(column, "name", None), _anonymous_label) for column in (left, right)):
        return False
    return left.compare(right)


@dataclass
class AggregationFunctionInfo:
    """A SQL aggregate function and how to apply it."""

    functions_map: ClassVar[dict[str, FunctionGenerator]] = {
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
    sqla_function: FunctionGenerator
    apply_on_column: bool
    """False for a function called without a column, such as ``count()``."""
    visitor: _FunctionVisitor | None = None
    """Transforms the function expression once built."""

    @classmethod
    def from_name(cls, name: str, visitor: _FunctionVisitor | None = None) -> Self:
        """Builds the function info of an aggregate function name.

        Raises:
            TranspilingError: If ``name`` is not a known function.
        """
        if name not in cls.functions_map:
            msg = f"Unknown function {name}"
            raise TranspilingError(msg)
        apply_on_column = name != "count"
        return cls(sqla_function=cls.functions_map[name], apply_on_column=apply_on_column, visitor=visitor)

    def apply(self, *args: QueryableAttribute[Any] | ColumnElement[Any]) -> ColumnElement[Any]:
        """Calls the function on ``args``, then ``visitor`` on the result if set."""
        func = self.sqla_function(*args)
        if self.visitor:
            func = self.visitor(func)
        return func


@dataclass(frozen=True)
class _ColumnTransform:
    """A selected column wrapped in a SQL expression, such as a JSON extraction, with its query node."""

    attribute: QueryableAttribute[Any]
    node: QueryNodeType

    @classmethod
    def _new(cls, attribute: Function[Any] | QueryableAttribute[Any], node: QueryNodeType) -> Self:
        """Labels ``attribute`` anonymously and pairs it with ``node``."""
        return cls(attribute.label(None), node)

    @classmethod
    def extract_json(cls, attribute: QueryableAttribute[Any], node: QueryNodeType, scope: AliasContext[Any]) -> Self:
        """Extracts the JSON path of ``node`` from a JSON column, giving an empty object when the value is missing."""
        if scope.dialect == "postgresql":
            transform = func.coalesce(
                func.jsonb_path_query_first(attribute, sqla_cast(node.metadata.data.json_path, postgresql.JSONPATH)),
                sqla_cast({}, postgresql.JSONB),
            )
        else:
            transform = func.coalesce(attribute.op("->")(node.metadata.data.json_path), func.json_object())
        return cls._new(transform, node)


class _NodeInspect:
    """Gives the aliased columns, foreign keys, aggregate functions and labels of one query node.

    Get one with ``AliasContext.inspect(node)``.
    """

    def __init__(self, node: QueryNodeType, scope: AliasContext[Any]) -> None:
        self.node = node
        self.scope = scope

    def _foreign_keys_selection(self, alias: AliasedClass[Any] | None = None) -> list[QueryableAttribute[Any]]:
        """Returns the local foreign keys of the node's child relationships, which their joins need.

        Columns are read from ``alias``, or from the node's parent alias when ``None``.
        """
        selected_fks: list[QueryableAttribute[Any]] = []
        alias_insp = inspect(alias or self.scope.alias_from_relation_node(self.node, "parent"))
        for child in self.node.children:
            if not child.value.is_relation or not isinstance(child.value.model_field.property, RelationshipProperty):
                continue
            for column in child.value.model_field.property.local_columns:
                if column.key is None:
                    continue
            selected_fks.extend(
                [
                    alias_insp.mapper.attrs[column.key].class_attribute.adapt_to_entity(alias_insp)
                    for column in child.value.model_field.property.local_columns
                    if column.key is not None
                ]
            )
        return selected_fks

    def _transform_column(
        self, node: QueryNodeType, attribute: QueryableAttribute[Any]
    ) -> QueryableAttribute[Any] | _ColumnTransform:
        """Wraps ``attribute`` in a JSON extraction when ``node`` has a JSON path."""
        transform: _ColumnTransform | None = None
        if node.metadata.data.json_path:
            transform = _ColumnTransform.extract_json(attribute, node, self.scope)
        return attribute if transform is None else transform

    @property
    def children(self) -> list[_NodeInspect]:
        """The node's children, inspected within the same context."""
        return [_NodeInspect(child, self.scope) for child in self.node.children]

    @property
    def value(self) -> GraphQLFieldDefinition:
        """Shortcut for ``self.node.value``."""
        return self.node.value

    @property
    def mapper(self) -> Mapper[Any]:
        """Mapper of the related model for a model field, of the node's own model otherwise."""
        if self.value.has_model_field:
            return self.value.model_field.property.mapper.mapper
        return self.value.model.__mapper__

    @property
    def key(self) -> str:
        """Label key of the node: its function name, if any, then its table name (root) or field key."""
        prefix = f"{function.function}_" if (function := self.value.function()) else ""
        if self.node.is_root:
            suffix = self.value.model.__tablename__
        else:
            suffix = self.value.model_field.key if self.value.has_model_field else ""
        return f"{prefix}{suffix}"

    @property
    def name(self) -> str:
        """Label name of the node: its key, prefixed by its parent's key so that it is unique across levels."""
        if self.node.parent and (parent_key := _NodeInspect(self.node.parent, self.scope).key):
            return f"{parent_key}__{self.key}"
        return self.key

    @property
    def is_data_root(self) -> bool:
        """Whether the node selects rows of the root alias.

        That is the root node or, in a query that also selects root aggregations, the ``nodes`` list under the root.
        """
        return bool(
            (
                self.node.graph_metadata.metadata.root_aggregations
                and self.value.name == NODES_KEY
                and self.node.parent
                and self.node.parent.is_root
            )
            or self.node.is_root
        )

    def output_functions(
        self,
        alias: AliasedClass[Any],
        visit_func: _FunctionVisitor = lambda func: func,
    ) -> dict[QueryNodeType, Label[Any]]:
        """Builds the labelled aggregate function columns to select, with arguments read from ``alias``.

        A function taking a column gets one column per argument node; ``count()`` gets one for the node itself.
        ``visit_func`` is applied to each function before labelling, for instance to add ``.over()``.
        """
        functions: dict[QueryNodeType, Label[Any]] = {}
        function_info = AggregationFunctionInfo.from_name(self.value.function(strict=True).function, visitor=visit_func)
        if function_info.apply_on_column:
            for arg_child in self.children:
                arg = self.mapper.attrs[arg_child.value.model_field_name].class_attribute.adapt_to_entity(
                    inspect(alias)
                )
                functions[arg_child.node] = function_info.apply(arg).label(None)
        else:
            functions[self.node] = visit_func(function_info.sqla_function()).label(None)
        return functions

    def filter_function(
        self, alias: AliasedClass[Any], distinct: bool | None = None
    ) -> tuple[QueryNodeType, Label[Any]]:
        """Builds the labelled aggregate function column of a WHERE predicate, with arguments read from ``alias``.

        Returns:
            The argument node when there is exactly one, otherwise the node itself, and the column.
        """
        function_info = AggregationFunctionInfo.from_name(self.value.function(strict=True).function)
        function_args = []
        argument_attributes = [
            self.mapper.attrs[arg_child.value.model_field_name].class_attribute.adapt_to_entity(inspect(alias))
            for arg_child in self.children
        ]
        function_args = (sqla_distinct(*argument_attributes),) if distinct else argument_attributes
        function_node = self.children[0].node if len(self.children) == 1 else self.node
        return function_node, function_info.apply(*function_args).label(None)

    def columns(
        self, alias: AliasedClass[Any] | None = None
    ) -> tuple[list[QueryableAttribute[Any]], list[_ColumnTransform]]:
        """Returns the node's selected columns and JSON extractions, plus its primary keys so rows can be identified.

        Columns are read from ``alias``, or from the alias inferred from the node when ``None``.
        """
        columns: list[QueryableAttribute[Any]] = []
        transforms: list[_ColumnTransform] = []
        property_set: set[MapperProperty[Any]] = set()
        for child in self.node.children:
            if not child.value.is_relation and not child.value.is_computed:
                aliased = self.scope.aliased_attribute(child, alias)
                property_set.add(aliased.property)
                aliased = self._transform_column(child, aliased)
                if isinstance(aliased, _ColumnTransform):
                    transforms.append(aliased)
                else:
                    columns.append(aliased)

        id_attributes = self.scope.aliased_id_attributes(self.node, alias)
        columns.extend(attribute for attribute in id_attributes if attribute.property not in property_set)
        return columns, transforms

    def foreign_key_columns(
        self, side: RelationshipSide, alias: AliasedClass[Any] | None = None
    ) -> list[QueryableAttribute[Any]]:
        """Returns the local (``"parent"``) or remote (``"target"``) foreign keys of the node's relationship.

        Columns are read from ``alias``, or from the alias inferred from the node and ``side`` when ``None``.
        """
        alias_insp = inspect(alias or self.scope.alias_from_relation_node(self.node, side))
        relationship = self.node.value.model_field.property
        assert isinstance(relationship, RelationshipProperty)
        columns = relationship.local_columns if side == "parent" else relationship.remote_side
        return [
            alias_insp.mapper.attrs[column.key].class_attribute.adapt_to_entity(alias_insp)
            for column in columns
            if column.key is not None
        ]

    def selection(self, alias: AliasedClass[Any] | None = None) -> list[QueryableAttribute[Any]]:
        """Returns the plain columns to select for the node, plus the foreign keys its child relations join on."""
        columns, _ = self.columns(alias)
        return [*columns, *self._foreign_keys_selection(alias)]


class AliasContext(Generic[DeclarativeT]):
    """Maps the query nodes of one query to SQLAlchemy aliases.

    Each ``(node, relationship side)`` gets one alias, reused by every reference to it, so the generated SQL has no
    naming conflicts. ``sub`` creates the context of a related model sharing these aliases; ``replace`` swaps the
    root alias in place, for queries wrapped in a pagination subquery.
    """

    def __init__(
        self,
        model: type[DeclarativeT],
        dialect: SupportedDialect,
        *,
        root_alias: AliasedClass[DeclarativeBase] | None = None,
        parent: AliasContext[Any] | None = None,
        alias_map: dict[tuple[QueryNodeType, RelationshipSide], AliasedClass[Any]] | None = None,
        inspector: SQLAlchemyInspector | None = None,
    ) -> None:
        """Creates the context of ``model``, rooted on ``root_alias`` or on an alias named after its table.

        ``parent`` is the context this one is nested in, and ``alias_map`` the aliases it shares with other contexts of
        the same query.
        """
        self._parent: AliasContext[Any] | None = parent
        self._root_alias = (
            root_alias if root_alias is not None else aliased(model.__mapper__, name=model.__tablename__, flat=True)
        )
        self._node_alias_map: dict[tuple[QueryNodeType, RelationshipSide], AliasedClass[Any]] = alias_map or {}
        self._inspector = inspector or SQLAlchemyInspector([model.registry])

        self.dialect: SupportedDialect = dialect
        self.model = model
        self.level: int = self._parent.level + 1 if self._parent else 0

    @property
    def is_root(self) -> bool:
        """Whether this context has no parent."""
        return self._parent is None

    @property
    def root_alias(self) -> AliasedClass[Any]:
        """Alias the query selects from."""
        return self._root_alias

    def inspect(self, node: QueryNodeType) -> _NodeInspect:
        """Returns the inspector of ``node`` within this context."""
        return _NodeInspect(node, self)

    def alias_from_relation_node(self, node: QueryNodeType, side: RelationshipSide) -> AliasedClass[Any]:
        """Returns the alias of one side of a relation, created on first use and reused afterwards.

        The root alias is returned for a node that selects root rows, or for the ``"parent"`` side of its children.

        Raises:
            TranspilingError: If ``node`` is not a relation node.
        """
        node_inspect = self.inspect(node)
        if (side == "parent" and node.parent and self.inspect(node.parent).is_data_root) or node_inspect.is_data_root:
            return self._root_alias
        if not node.value.is_relation:
            msg = "Node must be a relation node"
            raise TranspilingError(msg)
        attribute = node.value.model_field
        if (alias := self._node_alias_map.get((node, side))) is not None:
            return alias
        mapper = attribute.parent.mapper if side == "parent" else attribute.entity.mapper
        alias = aliased(mapper.class_, flat=True)
        self.set_relation_alias(node, side, alias)
        return alias

    def aliased_attribute(self, node: QueryNodeType, alias: AliasedClass[Any] | None = None) -> QueryableAttribute[Any]:
        """Returns the node's model field read from ``alias``, or from the alias inferred from the node.

        A column is read from its parent's alias. A relation is read from its parent's alias and pointed at its own
        alias with ``of_type``.
        """
        model_field: QueryableAttribute[RelationshipProperty[Any]] = node.value.model_field
        if alias is not None:
            return model_field.adapt_to_entity(inspect(alias))
        parent = node.find_parent(lambda node: not node.value.is_computed, strict=True)
        if model_field.parent.is_aliased_class:
            return model_field
        if not node.value.is_relation:
            parent_alias = self.alias_from_relation_node(parent, "target")
            return model_field.adapt_to_entity(inspect(parent_alias))
        parent_alias = (
            self._root_alias if self.inspect(parent).is_data_root else self.alias_from_relation_node(parent, "target")
        )
        model_field = model_field.adapt_to_entity(inspect(parent_alias))
        child_alias = self.alias_from_relation_node(node, "target")
        return model_field.of_type(child_alias)

    def aliased_id_attributes(
        self, node: QueryNodeType, alias: AliasedClass[Any] | None = None
    ) -> list[QueryableAttribute[Any]]:
        """Returns the node's primary keys read from ``alias``, or from the root or relation alias of the node."""
        mapper = inspect(self._root_alias).mapper if node.is_root else self.inspect(node).mapper
        columns = SQLAlchemyInspector.pk_attributes(mapper)
        if alias is not None:
            return [pk_attribute.adapt_to_entity(inspect(alias)) for pk_attribute in columns]

        if node.is_root:
            columns = [pk_attribute.adapt_to_entity(inspect(self._root_alias)) for pk_attribute in columns]
        else:
            parent_alias = self.alias_from_relation_node(node, "target")
            columns = [pk_attribute.adapt_to_entity(inspect(parent_alias)) for pk_attribute in columns]

        return columns

    def scoped_column(self, clause: Select[Any] | FromClause, column_name: str) -> ColumnElement[Any]:
        """Returns a column of ``clause`` by name, unlabelled since callers match columns by object."""
        columns = clause.selected_columns if isinstance(clause, Select) else clause.columns
        return columns[column_name]

    def set_relation_alias(self, node: QueryNodeType, side: RelationshipSide, alias: AliasedClass[Any]) -> None:
        """Sets the alias used for one side of a relation."""
        self._node_alias_map[(node, side)] = alias

    def id_field_definitions(self, model: type[DeclarativeBase]) -> list[GraphQLFieldDefinition]:
        """Returns the GraphQL field definitions of the primary keys of ``model``."""
        root = QueryNode.root_node(model)
        return [
            GraphQLFieldDefinition.from_field(self._inspector.field_definition(pk, DTOConfig(Purpose.READ)))
            for pk in self.aliased_id_attributes(root)
        ]

    def replace(self, model: type[DeclarativeT] | None = None, alias: AliasedClass[Any] | None = None) -> None:
        """Changes the model and root alias in place; ``None`` keeps the current one.

        Changing in place lets every holder of this context, such as ``PlanContext.build_join``, see the new root.
        """
        if model is not None:
            self.model = model
        if alias is not None:
            self._root_alias = alias

    def sub(self, model: type[DeclarativeSubT], alias: AliasedClass[Any]) -> AliasContext[DeclarativeSubT]:
        """Creates the context of a related model, one level down, sharing this context's aliases."""
        return AliasContext(
            model=model,
            root_alias=alias,
            parent=self,
            alias_map=self._node_alias_map,
            inspector=self._inspector,
            dialect=self.dialect,
        )

    @override
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.model},{self.level}>"
