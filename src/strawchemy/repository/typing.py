from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeAlias, TypeVar

if TYPE_CHECKING:
    from collections import OrderedDict
    from collections.abc import Callable

    from sqlalchemy import Function
    from sqlalchemy.ext.asyncio import AsyncSession, async_scoped_session
    from sqlalchemy.orm import DeclarativeBase, Session, scoped_session
    from sqlalchemy.sql import SQLColumnExpression
    from strawberry import Info

    from strawchemy.dto.strawberry import OrderByEnum
    from strawchemy.schema.filters import GraphQLComparison
    from strawchemy.transpiler import QueryExecutor, QueryHook


__all__ = (
    "AnyAsyncSession",
    "AnySession",
    "AnySyncSession",
    "DeclarativeSubT",
    "DeclarativeT",
    "FunctionGenerator",
    "QueryExecutorT",
    "QueryHookCallable",
    "RelationshipSide",
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
FunctionGenerator: TypeAlias = "Callable[..., Function[Any]]"
QueryHookCallable: TypeAlias = "QueryHook[QueryHookDeclarativeT]"
FilterMap: TypeAlias = "OrderedDict[tuple[type[Any], ...], type[GraphQLComparison]]"
AnySyncSession: TypeAlias = "Session | scoped_session[Session]"
AnyAsyncSession: TypeAlias = "AsyncSession | async_scoped_session[AsyncSession]"
AnySession: TypeAlias = "AnySyncSession | AnyAsyncSession"
OrderBySpec: TypeAlias = "tuple[SQLColumnExpression[Any], OrderByEnum]"
AsyncSessionGetter: TypeAlias = "Callable[[Info[Any, Any]], AnyAsyncSession]"
SyncSessionGetter: TypeAlias = "Callable[[Info[Any, Any]], AnySyncSession]"
AnySessionGetter: TypeAlias = "AsyncSessionGetter | SyncSessionGetter"
