from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeAlias, TypedDict, TypeVar

if TYPE_CHECKING:
    from collections import OrderedDict
    from collections.abc import Callable

    from sqlalchemy import Column, ColumnElement, Function, TextClause
    from sqlalchemy.ext.asyncio import AsyncSession, async_scoped_session
    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute, RelationshipProperty, Session, scoped_session
    from sqlalchemy.sql.type_api import TypeEngine
    from strawchemy.graphql.dto import OrderByNode, QueryNode

    from ._executor import QueryExecutor
    from .filters import SQLAlchemyFilterBase
    from .hook import QueryHook


__all__ = (
    "AnyAsyncSession",
    "AnySession",
    "AnySyncSession",
    "ColumnDescription",
    "ColumnOrRelationship",
    "DeclarativeSubT",
    "DeclarativeT",
    "FunctionGenerator",
    "QueryExecutorT",
    "QueryHookCallable",
    "RelationshipSide",
    "SQLAlchemyOrderByNode",
    "SQLAlchemyQueryNode",
    "SessionT",
    "StatementType",
)

DeclarativeT = TypeVar("DeclarativeT", bound="DeclarativeBase")
DeclarativeSubT = TypeVar("DeclarativeSubT", bound="DeclarativeBase")
QueryHookDeclarativeT = TypeVar("QueryHookDeclarativeT", bound="DeclarativeBase")
SessionT = TypeVar("SessionT", bound="AnySession")
QueryExecutorT = TypeVar("QueryExecutorT", bound="QueryExecutor[Any]")

RelationshipSide: TypeAlias = Literal["parent", "target"]
StatementType = Literal["lambda", "select"]
LoadMode = Literal["load_options", "statement"]
SQLAlchemyQueryNode: TypeAlias = "QueryNode[DeclarativeBase, QueryableAttribute[Any]]"
SQLAlchemyOrderByNode: TypeAlias = "OrderByNode[DeclarativeBase, QueryableAttribute[Any]]"
type ColumnOrRelationship = "Column[Any] | RelationshipProperty[Any]"
FunctionGenerator: TypeAlias = "Callable[..., Function[Any]]"
QueryHookCallable: TypeAlias = "QueryHook[QueryHookDeclarativeT]"
FilterMap: TypeAlias = "OrderedDict[tuple[type[Any], ...], type[SQLAlchemyFilterBase]]"
AnySyncSession: TypeAlias = "Session | scoped_session[Session]"
AnyAsyncSession: TypeAlias = "AsyncSession | async_scoped_session[AsyncSession]"
AnySession: TypeAlias = "AnySyncSession | AnyAsyncSession"


class ColumnDescription(TypedDict):
    name: str | None
    type: TypeEngine[Any]
    expr: ColumnElement[Any] | TextClause
