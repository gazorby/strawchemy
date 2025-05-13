"""Custom DTO implementation."""

from __future__ import annotations

from .config.base import StrawchemyConfig
from .input import Input
from .mapper import Strawchemy
from .sqlalchemy.hook import QueryHook
from .strawberry import ModelInstance
from .strawberry.repository import StrawchemyAsyncRepository, StrawchemySyncRepository
from .strawberry.types import (
    ErrorType,
    RequiredToManyUpdateInput,
    RequiredToOneInput,
    ToManyCreateInput,
    ToManyUpdateInput,
    ToOneInput,
    ValidationErrorType,
)
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
