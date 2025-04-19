"""Custom DTO implementation."""

from __future__ import annotations

from .graphql.mutation import Input
from .mapper import Strawchemy
from .sqlalchemy.hook import QueryHook
from .strawberry import ModelInstance
from .strawberry.repository import StrawchemyAsyncRepository, StrawchemySyncRepository
from .strawberry.types import (
    RequiredToManyUpdateInput,
    RequiredToOneInput,
    ToManyCreateInput,
    ToManyUpdateInput,
    ToOneInput,
    ValidationErrorType,
)

__all__ = (
    "Input",
    "ModelInstance",
    "QueryHook",
    "RequiredToManyUpdateInput",
    "RequiredToOneInput",
    "Strawchemy",
    "StrawchemyAsyncRepository",
    "StrawchemySyncRepository",
    "ToManyCreateInput",
    "ToManyUpdateInput",
    "ToOneInput",
    "ValidationErrorType",
)
