from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawberry.types import get_object_definition
from tests.unit.models import User

if TYPE_CHECKING:
    from strawchemy.mapper import Strawchemy

TYPE_DECORATOR_NAMES: list[str] = [
    "type",
    "input",
    "filter_input",
    "aggregate_filter_input",
    "order_by_input",
    "aggregation_type",
]


@pytest.mark.parametrize("decorator", TYPE_DECORATOR_NAMES)
def test_type_no_purpose_excluded(
    decorator: str, strawchemy: Strawchemy[DeclarativeBase, QueryableAttribute[Any]]
) -> None:
    @getattr(strawchemy, decorator)(User, include="all", override=True)
    class UserType: ...

    type_def = get_object_definition(UserType, strict=True)
    assert type_def.get_field("private") is None
