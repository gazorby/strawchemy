"""Custom DTO implementation."""

from __future__ import annotations

from strawchemy.config.base import StrawchemyConfig
from strawchemy.instance import ModelInstance
from strawchemy.mapper import Strawchemy
from strawchemy.repository.strawberry import StrawchemyAsyncRepository, StrawchemySyncRepository
from strawchemy.schema.interfaces import ErrorType
from strawchemy.schema.mutation import (
    Input,
    RequiredToManyUpdateInput,
    RequiredToOneInput,
    ToManyCreateInput,
    ToManyUpdateInput,
    ToOneInput,
    ValidationErrorType,
)
from strawchemy.transpiler.hook import QueryHook
from strawchemy.validation import InputValidationError

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
