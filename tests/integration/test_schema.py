from __future__ import annotations

from strawberry import Schema

from .fixtures import scalar_overrides
from .types import mysql, postgres


def test_schema() -> None:
    for types in (postgres, mysql):
        Schema(query=types.AsyncQuery, mutation=types.AsyncMutation, scalar_overrides=scalar_overrides)
