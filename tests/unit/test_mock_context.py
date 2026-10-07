from __future__ import annotations

import pytest

from strawchemy.typing import SupportedDialect
from tests.unit.utils import MockContext


@pytest.mark.parametrize("dialect", ["postgresql", "sqlite", "mysql"])
def test_mock_context_session_reports_dialect(dialect: SupportedDialect) -> None:
    assert MockContext(dialect).session.get_bind().dialect.name == dialect
