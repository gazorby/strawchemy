"""Custom DTO implementation."""

from __future__ import annotations

from strawchemy.config.base import StrawchemyConfig
from strawchemy.mapper import Strawchemy
from strawchemy.sqlalchemy.hook import QueryHook
from strawchemy.strawberry import ModelInstance
from strawchemy.strawberry.mutation.input import Input
from strawchemy.strawberry.mutation.types import (
    ErrorType,
    RequiredToManyUpdateInput,
    RequiredToOneInput,
    ToManyCreateInput,
    ToManyUpdateInput,
    ToOneInput,
    ValidationErrorType,
)
from strawchemy.strawberry.repository import StrawchemyAsyncRepository, StrawchemySyncRepository
from strawchemy.validation.base import InputValidationError

__all__ = (
    "ErrorType",
    "Input",
    "InputValidationError",
    "ModelInstance",
    "QueryHook",
    "RequiredToManyUpdateInput",
    "RequiredToOneInput",
    "Strawchemy",
    "StrawchemyAsyncRepository",
    "StrawchemyConfig",
    "StrawchemySyncRepository",
    "ToManyCreateInput",
    "ToManyUpdateInput",
    "ToOneInput",
    "ValidationErrorType",
)
