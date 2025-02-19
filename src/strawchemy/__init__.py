"""Custom DTO implementation."""

from __future__ import annotations

from .mapper import Strawchemy
from .sqlalchemy.hook import QueryHook
from .strawberry import ModelInstance
from .strawberry.repository import StrawchemyAsyncRepository

__all__ = ("ModelInstance", "QueryHook", "StrawchemyAsyncRepository", "strawchemy")


strawchemy = Strawchemy()
