"""Custom DTO implementation."""

from __future__ import annotations

from .config.base import StrawchemyConfig
from .mapper import Strawchemy
from .sqlalchemy.hook import QueryHook
from .strawberry import ModelInstance
from .strawberry.mutation.input import Input
from .strawberry.mutation.types import (
    ErrorType,
    RequiredToManyUpdateInput,
    RequiredToOneInput,
    ToManyCreateInput,
    ToManyUpdateInput,
    ToOneInput,
    ValidationErrorType,
)
from .strawberry.repository import StrawchemyAsyncRepository, StrawchemySyncRepository
from .validation.base import InputValidationError

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
