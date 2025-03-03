from __future__ import annotations

from dataclasses import dataclass

__all__ = ("DefaultOffsetPagination",)


@dataclass
class DefaultOffsetPagination:
    limit: int | None = None
    offset: int = 0
