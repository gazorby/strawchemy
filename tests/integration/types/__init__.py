from __future__ import annotations

from typing import TypeAlias, Union

from . import mysql, postgres, sqlite

__all__ = ("AnyAsyncMutationType", "AnyAsyncQueryType", "AnySyncMutationType", "AnySyncQueryType")

AnyAsyncQueryType: TypeAlias = Union[Union[postgres.AsyncQuery, mysql.AsyncQuery], sqlite.AsyncQuery]
AnySyncQueryType: TypeAlias = Union[Union[postgres.SyncQuery, mysql.SyncQuery], sqlite.SyncQuery]
AnyAsyncMutationType: TypeAlias = Union[Union[postgres.AsyncMutation, mysql.AsyncMutation], sqlite.AsyncMutation]
AnySyncMutationType: TypeAlias = Union[Union[postgres.SyncMutation, mysql.SyncMutation], sqlite.SyncMutation]
