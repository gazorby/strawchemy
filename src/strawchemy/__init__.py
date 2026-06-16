"""Custom DTO implementation."""

from __future__ import annotations

from strawchemy.config.base import StrawchemyConfig
from strawchemy.dto.types import ALL, RELATIONSHIPS, SCALARS, FieldGroup
from strawchemy.instance import ModelInstance
from strawchemy.mapper import Strawchemy
from strawchemy.repository.strawberry import StrawchemyAsyncRepository, StrawchemySyncRepository
from strawchemy.schema.filters import (
    ArrayComparison,
    DateComparison,
    DateTimeComparison,
    EqualityComparison,
    GraphQLComparison,
    OrderComparison,
    TextComparison,
    TimeComparison,
    TimeDeltaComparison,
)
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
    "ALL",
    "RELATIONSHIPS",
    "SCALARS",
    "ArrayComparison",
    "DateComparison",
    "DateTimeComparison",
    "EqualityComparison",
    "ErrorType",
    "FieldGroup",
    "GraphQLComparison",
    "Input",
    "InputValidationError",
    "ModelInstance",
    "OrderComparison",
    "QueryHook",
    "RequiredToManyUpdateInput",
    "RequiredToOneInput",
    "Strawchemy",
    "StrawchemyAsyncRepository",
    "StrawchemyConfig",
    "StrawchemySyncRepository",
    "TextComparison",
    "TimeComparison",
    "TimeDeltaComparison",
    "ToManyCreateInput",
    "ToManyUpdateInput",
    "ToOneInput",
    "ValidationErrorType",
)
