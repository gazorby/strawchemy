from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from strawchemy.typing import SupportedDialect

__all__ = ("MockContext",)


@dataclass
class MockContext:
    dialect: SupportedDialect
    session: MagicMock = field(init=False)

    def __post_init__(self) -> None:
        dialect = MagicMock(name="DialectMock")
        dialect.name = "postgresql"
        engine = MagicMock(name="EngineMock", dialect=dialect)
        self.session = MagicMock(name="SessionMock", get_bind=MagicMock(return_value=engine))
