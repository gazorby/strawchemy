"""Custom DTO implementation."""

from __future__ import annotations

from strawchemy.config.base import StrawchemyConfig
from strawchemy.instance import ModelInstance
from strawchemy.mapper import Strawchemy
from strawchemy.mutation import (
    ErrorType,
    RequiredToManyUpdateInput,
    RequiredToOneInput,
    ToManyCreateInput,
    ToManyUpdateInput,
    ToOneInput,
    ValidationErrorType,
)
from strawchemy.mutation.input import Input
from strawchemy.repository.strawberry import StrawchemyAsyncRepository, StrawchemySyncRepository
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
