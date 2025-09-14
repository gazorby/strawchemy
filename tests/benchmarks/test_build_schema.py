from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pytest_lazy_fixtures import lf

from tests.integration.models import User

if TYPE_CHECKING:
    from strawchemy import Strawchemy


@pytest.mark.benchmark(group="schema")
@pytest.mark.parametrize("strawchemy", [lf("strawchemy_postgresql"), lf("strawchemy_sqlite"), lf("strawchemy_mysql")])
def test_build_user_type(strawchemy: Strawchemy) -> None:
    strawchemy.type(User, include="all", override=True)(type("UserType", (), {}))
