from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from pytest_lazy_fixtures import lf
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from graphql import GraphQLError
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from strawberry.scalars import JSON
from tests.typing import AnyQueryExecutor, SyncQueryExecutor
from tests.utils import generate_query, maybe_async

from .models import Color, Fruit, User, metadata
from .types import (
    ColorType,
    FruitFilter,
    FruitOrderBy,
    FruitTypeWithPaginationAndOrderBy,
    UserFilter,
    UserOrderBy,
    UserType,
    strawchemy,
)
from .typing import RawRecordData

if TYPE_CHECKING:
    from pytest import FixtureRequest

    from sqlalchemy import Engine


pytestmark = [pytest.mark.integration]

scalar_overrides: dict[object, Any] = {dict[str, Any]: JSON}


@strawberry.type
class AsyncQuery:
    fruit: FruitTypeWithPaginationAndOrderBy = strawchemy.field(repository_type=StrawchemyAsyncRepository)
    fruits: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter, order_by=FruitOrderBy, repository_type=StrawchemyAsyncRepository
    )
    fruits_paginated: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter,
        order_by=FruitOrderBy,
        pagination=True,
        repository_type=StrawchemyAsyncRepository,
    )
    fruits_aggregations: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter, order_by=FruitOrderBy, repository_type=StrawchemyAsyncRepository
    )
    fruits_aggregations_paginated: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter,
        order_by=FruitOrderBy,
        pagination=True,
        repository_type=StrawchemyAsyncRepository,
    )
    user: UserType = strawchemy.field(repository_type=StrawchemyAsyncRepository)
    users: list[UserType] = strawchemy.field(
        filter_input=UserFilter,
        order_by=UserOrderBy,
        pagination=True,
        repository_type=StrawchemyAsyncRepository,
    )
    colors: list[ColorType] = strawchemy.field(repository_type=StrawchemyAsyncRepository)


@strawberry.type
class SyncQuery:
    fruit: FruitTypeWithPaginationAndOrderBy = strawchemy.field(repository_type=StrawchemySyncRepository)
    fruits: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter, order_by=FruitOrderBy, repository_type=StrawchemySyncRepository
    )
    fruits_paginated: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter, order_by=FruitOrderBy, pagination=True, repository_type=StrawchemySyncRepository
    )
    fruits_aggregations: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter, order_by=FruitOrderBy, repository_type=StrawchemySyncRepository
    )
    fruits_aggregations_paginated: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter, order_by=FruitOrderBy, pagination=True, repository_type=StrawchemySyncRepository
    )
    user: UserType = strawchemy.field(repository_type=StrawchemySyncRepository)
    users: list[UserType] = strawchemy.field(
        filter_input=UserFilter, order_by=UserOrderBy, pagination=True, repository_type=StrawchemySyncRepository
    )
    colors: list[ColorType] = strawchemy.field()


@pytest.fixture
def raw_colors() -> RawRecordData:
    return [
        {"id": str(uuid4()), "name": "Red"},
        {"id": str(uuid4()), "name": "Yellow"},
        {"id": str(uuid4()), "name": "Orange"},
        {"id": str(uuid4()), "name": "Green"},
        {"id": str(uuid4()), "name": "Pink"},
    ]


@pytest.fixture
def raw_fruits(raw_colors: RawRecordData) -> RawRecordData:
    return [
        {
            "id": str(uuid4()),
            "name": "Apple",
            "color_id": raw_colors[0]["id"],
            "sweetness": 7,
            "has_core": True,
            "adjectives": ["crisp", "juicy", "sweet"],
            "price_decimal": Decimal("1.99"),
            "price_float": 1.99,
        },
        {
            "id": str(uuid4()),
            "name": "Banana",
            "color_id": raw_colors[1]["id"],
            "sweetness": 8,
            "has_core": False,
            "adjectives": ["soft", "sweet", "tropical"],
            "price_decimal": Decimal("0.89"),
            "price_float": 0.89,
        },
        {
            "id": str(uuid4()),
            "name": "Orange",
            "color_id": raw_colors[2]["id"],
            "sweetness": 6,
            "has_core": False,
            "adjectives": ["tangy", "juicy", "citrusy"],
            "price_decimal": Decimal("1.29"),
            "price_float": 1.29,
        },
        {
            "id": str(uuid4()),
            "name": "Strawberry",
            "color_id": raw_colors[3]["id"],
            "sweetness": 9,
            "has_core": False,
            "adjectives": ["sweet", "fragrant", "small"],
            "price_decimal": Decimal("2.49"),
            "price_float": 2.49,
        },
        {
            "id": str(uuid4()),
            "name": "Watermelon",
            "color_id": raw_colors[4]["id"],
            "sweetness": 8,
            "has_core": True,
            "adjectives": ["juicy", "refreshing", "summery"],
            "price_decimal": Decimal("4.99"),
            "price_float": 4.99,
        },
    ]


@pytest.fixture
def raw_users() -> RawRecordData:
    return [
        {
            "id": str(uuid4()),
            "name": "Alice",
            "settings": {"theme": "dark", "notifications": True},
            "birthday": date(1990, 5, 15),
            "newsletter_send_time": time(8, 0),
        },
        {
            "id": str(uuid4()),
            "name": "Bob",
            "settings": {"theme": "light", "notifications": False},
            "birthday": date(1985, 10, 22),
            "newsletter_send_time": time(9, 30),
        },
        {
            "id": str(uuid4()),
            "name": "Charlie",
            "settings": {"theme": "auto", "notifications": True},
            "birthday": date(1995, 3, 8),
            "newsletter_send_time": time(7, 15),
        },
    ]


@pytest.fixture
def seed_db_sync(
    engine: Engine, raw_fruits: RawRecordData, raw_colors: RawRecordData, raw_users: RawRecordData
) -> None:
    with engine.begin() as conn:
        metadata.drop_all(conn)
        metadata.create_all(conn)
        conn.execute(insert(Color).values(raw_colors))
        conn.execute(insert(Fruit).values(raw_fruits))
        conn.execute(insert(User).values(raw_users))


@pytest.fixture
async def seed_db_async(
    async_engine: AsyncEngine, raw_fruits: RawRecordData, raw_colors: RawRecordData, raw_users: RawRecordData
) -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
        await conn.execute(insert(Color).values(raw_colors))
        await conn.execute(insert(Fruit).values(raw_fruits))
        await conn.execute(insert(User).values(raw_users))


@pytest.fixture(params=[lf("async_session"), lf("session")], ids=["async", "sync"])
def any_query(request: FixtureRequest) -> AnyQueryExecutor:
    if isinstance(request.param, AsyncSession):
        request.getfixturevalue("seed_db_async")
        return generate_query(session=request.param, query=AsyncQuery, scalar_overrides=scalar_overrides)
    request.getfixturevalue("seed_db_sync")

    return generate_query(session=request.param, query=SyncQuery, scalar_overrides=scalar_overrides)


@pytest.fixture
def no_session_query() -> SyncQueryExecutor:
    return generate_query(query=SyncQuery, scalar_overrides=scalar_overrides)


def test_required_id_single(no_session_query: SyncQueryExecutor) -> None:
    result = no_session_query("{ user { name } }")

    assert bool(result.errors)
    assert len(result.errors) == 1
    assert isinstance(result.errors[0], GraphQLError)
    assert (
        result.errors[0].message == "Field 'user' argument 'id' of type 'UUID!' is required, but it was not provided."
    )


async def test_single(any_query: AnyQueryExecutor, raw_users: RawRecordData) -> None:
    result = await maybe_async(
        any_query(
            """
        query GetUser($id: UUID!) {
          user(id: $id) {
            name
          }
        }
        """,
            {"id": raw_users[0]["id"]},
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["user"] == {"name": raw_users[0]["name"]}


async def test_many(any_query: AnyQueryExecutor, raw_users: RawRecordData) -> None:
    result = await maybe_async(any_query("{ users { name } }"))

    assert not result.errors
    assert result.data
    assert result.data["users"] == [
        {"name": raw_users[0]["name"]},
        {"name": raw_users[1]["name"]},
        {"name": raw_users[2]["name"]},
    ]


async def test_relation(any_query: AnyQueryExecutor, raw_colors: RawRecordData) -> None:
    result = await maybe_async(any_query("{ fruits { color { id } } }"))

    assert not result.errors
    assert result.data
    assert result.data["fruits"] == [
        {"color": {"id": raw_colors[0]["id"]}},
        {"color": {"id": raw_colors[1]["id"]}},
        {"color": {"id": raw_colors[2]["id"]}},
        {"color": {"id": raw_colors[3]["id"]}},
        {"color": {"id": raw_colors[4]["id"]}},
    ]


async def test_list_relation(any_query: AnyQueryExecutor, raw_fruits: RawRecordData) -> None:
    result = await maybe_async(any_query("{ colors { fruits { name id } } }"))

    assert not result.errors

    expected = [
        {
            "fruits": [{"name": "Apple", "id": raw_fruits[0]["id"]}],
        },
        {
            "fruits": [{"name": "Banana", "id": raw_fruits[1]["id"]}],
        },
        {
            "fruits": [{"name": "Orange", "id": raw_fruits[2]["id"]}],
        },
        {
            "fruits": [{"name": "Strawberry", "id": raw_fruits[3]["id"]}],
        },
        {
            "fruits": [{"name": "Watermelon", "id": raw_fruits[4]["id"]}],
        },
    ]

    assert result.data
    assert all(fruit in result.data["colors"] for fruit in expected)
