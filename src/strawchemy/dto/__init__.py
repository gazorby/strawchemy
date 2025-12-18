"""Custom DTO implementation."""

from __future__ import annotations

from strawchemy.dto.base import DTOFieldDefinition, ModelFieldT, ModelInspector, ModelT
from strawchemy.dto.types import DTOConfig, Purpose, PurposeConfig
from strawchemy.dto.utils import config, field

__all__ = (
    "DTOConfig",
    "DTOFieldDefinition",
    "ModelFieldT",
    "ModelInspector",
    "ModelT",
    "Purpose",
    "PurposeConfig",
    "config",
    "field",
)
