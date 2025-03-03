from __future__ import annotations

from dataclasses import dataclass

__all__ = ("DefaultOffsetPagination",)


@dataclass(eq=True, frozen=True)
class DefaultOffsetPagination:
    limit: int = 100
    offset: int = 0
