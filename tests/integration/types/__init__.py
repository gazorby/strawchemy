from __future__ import annotations

from typing import TypeAlias

from . import mysql, postgres

__all__ = ("AnyAsyncMutationType", "AnyAsyncQueryType", "AnySyncMutationType", "AnySyncQueryType")

AnyAsyncQueryType: TypeAlias = postgres.AsyncQuery | mysql.AsyncQuery
AnySyncQueryType: TypeAlias = postgres.SyncQuery | mysql.SyncQuery
AnyAsyncMutationType: TypeAlias = postgres.AsyncMutation | mysql.AsyncMutation
AnySyncMutationType: TypeAlias = postgres.SyncMutation | mysql.SyncMutation
