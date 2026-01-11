"""Custom DTO implementation."""

from __future__ import annotations

from strawchemy.dto.base import DTOFieldDefinition, MappedDTO, ModelFieldT, ModelT, ToMappedProtocol, VisitorProtocol
from strawchemy.dto.types import DTOConfig, Purpose, PurposeConfig
from strawchemy.dto.utils import config, field

__all__ = (
    "DTOConfig",
    "DTOFieldDefinition",
    "MappedDTO",
    "ModelFieldT",
    "ModelT",
    "Purpose",
    "PurposeConfig",
    "ToMappedProtocol",
    "VisitorProtocol",
    "config",
    "field",
)
