"""Custom DTO implementation."""

from __future__ import annotations

from .mapper import Strawchemy
from .sqlalchemy.hook import QueryHook
from .strawberry import ModelInstance
from .strawberry.repository import StrawchemyAsyncRepository, StrawchemySyncRepository

__all__ = ("ModelInstance", "QueryHook", "StrawchemyAsyncRepository", "StrawchemySyncRepository", "strawchemy")


strawchemy = Strawchemy()
