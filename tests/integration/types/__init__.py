from __future__ import annotations

from typing import TypeAlias

from . import postgres

AnyAsyncQueryType: TypeAlias = postgres.AsyncQuery
AnySyncQueryType: TypeAlias = postgres.SyncQuery
