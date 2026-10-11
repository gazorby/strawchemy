from __future__ import annotations

from operator import itemgetter
from typing import TYPE_CHECKING, Any

import pytest

from tests.integration.types import mysql as mysql_types
from tests.integration.types import postgres as postgres_types
from tests.integration.types import sqlite as sqlite_types
from tests.integration.typing import RawRecordData
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]


@pytest.fixture
def async_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.InterfaceAsyncQuery
    if dialect == "mysql":
        return mysql_types.InterfaceAsyncQuery
    return sqlite_types.InterfaceAsyncQuery


@pytest.fixture
def sync_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.InterfaceSyncQuery
    if dialect == "mysql":
        return mysql_types.InterfaceSyncQuery
    return sqlite_types.InterfaceSyncQuery


def _color_names(raw_colors: RawRecordData) -> dict[int, str]:
    return {color["id"]: color["name"] for color in raw_colors}


async def test_type_implementing_interface(
    any_query: AnyQueryExecutor, raw_fruits: RawRecordData, raw_colors: RawRecordData
) -> None:
    """Test that a type implementing an interface is queried, filtered and joined as its own type."""
    result = await maybe_async(
        any_query("""
            {
                fruits(filter: { name: { eq: "Apple" } }) {
                    __typename
                    name
                    color { __typename name }
                }
            }
        """)
    )

    assert not result.errors
    assert result.data
    apple = next(fruit for fruit in raw_fruits if fruit["name"] == "Apple")
    assert result.data["fruits"] == [
        {
            "__typename": "NamedFruitType",
            "name": "Apple",
            "color": {"__typename": "NamedColorType", "name": _color_names(raw_colors)[apple["color_id"]]},
        }
    ]


async def test_interface_field_resolves_implementing_type(
    any_query: AnyQueryExecutor, raw_fruits: RawRecordData, raw_colors: RawRecordData
) -> None:
    """Test that rows returned by an interface field resolve to the type implementing it."""
    result = await maybe_async(
        any_query("""
            {
                named {
                    __typename
                    name
                    ... on NamedFruitType { color { name } }
                }
            }
        """)
    )

    assert not result.errors
    assert result.data
    color_names = _color_names(raw_colors)
    expected = [
        {"__typename": "NamedFruitType", "name": fruit["name"], "color": {"name": color_names[fruit["color_id"]]}}
        for fruit in raw_fruits
    ]
    assert sorted(result.data["named"], key=itemgetter("name")) == sorted(expected, key=itemgetter("name"))
