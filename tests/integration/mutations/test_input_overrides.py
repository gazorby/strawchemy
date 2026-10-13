from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
import strawberry

from strawchemy import Input, StrawchemyAsyncRepository, StrawchemySyncRepository
from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import Color, Fruit
from tests.integration.utils import data_argument
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Fruit, include=["name", "color"], scope="schema")
    class FruitType: ...

    @strawchemy.type(Color, include=["name", "fruits"], scope="schema")
    class ColorType: ...

    @strawchemy.create_input(Fruit, include=["name", "sweetness", "water_percent"])
    class FruitCreateInput: ...

    @strawchemy.create_input(Color, include=["name"])
    class ColorCreateInput: ...

    # No case reads through it; a schema needs a query type.
    @strawberry.type
    class Query:
        colors: list[ColorType] = strawchemy.field()

    # test_column_override runs on async sessions only.
    @strawberry.type
    class AsyncMutation:
        @strawchemy.field(graphql_type=ColorType, arguments=data_argument(ColorCreateInput))
        async def create_blue_color(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
            return (
                await StrawchemyAsyncRepository(ColorType, info).create(Input(data, name="New Blue"))
            ).graphql_type()

        @strawchemy.field(graphql_type=ColorType, arguments=data_argument(ColorCreateInput))
        async def create_apple_color(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
            color_input = Input(data)
            color_input.instances[0].fruits.extend(
                [
                    Fruit(name="New Apple", sweetness=1, water_percent=0.4),
                    Fruit(name="New Strawberry", sweetness=1, water_percent=0.3),
                ]
            )
            return (await StrawchemyAsyncRepository(ColorType, info).create(color_input)).graphql_type()

        @strawchemy.field(graphql_type=ColorType, arguments=data_argument(ColorCreateInput))
        async def create_color_for_existing_fruits(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
            color_input = Input(data)
            session = cast("AsyncSession", info.context.session)
            apple, strawberry = (
                Fruit(name="New Apple", sweetness=1, water_percent=0.4),
                Fruit(name="New Strawberry", sweetness=1, water_percent=0.3),
            )
            session.add_all([apple, strawberry])
            await session.commit()
            session.expire(strawberry)
            color_input.instances[0].fruits.extend([apple, strawberry])
            return (await StrawchemyAsyncRepository(ColorType, info).create(color_input)).graphql_type()

        @strawchemy.field(graphql_type=FruitType, arguments=data_argument(FruitCreateInput))
        async def create_red_fruit(self, info: strawberry.Info, data: FruitCreateInput) -> FruitType:
            fruit_input = Input(data)
            fruit_input.instances[0].color = Color(name="New Red")
            return (await StrawchemyAsyncRepository(FruitType, info).create(fruit_input)).graphql_type()

        @strawchemy.field(graphql_type=FruitType, arguments=data_argument(FruitCreateInput))
        async def create_fruit_for_existing_color(self, info: strawberry.Info, data: FruitCreateInput) -> FruitType:
            fruit_input = Input(data)
            session = cast("AsyncSession", info.context.session)
            red = Color(name="New Red")
            session.add(red)
            await session.commit()
            fruit_input.instances[0].color = red
            return (await StrawchemyAsyncRepository(FruitType, info).create(fruit_input)).graphql_type()

    @strawberry.type
    class SyncMutation:
        @strawchemy.field(graphql_type=ColorType, arguments=data_argument(ColorCreateInput))
        def create_apple_color(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
            color_input = Input(data)
            color_input.instances[0].fruits.extend(
                [
                    Fruit(name="New Apple", sweetness=1, water_percent=0.4),
                    Fruit(name="New Strawberry", sweetness=1, water_percent=0.3),
                ]
            )
            return StrawchemySyncRepository(ColorType, info).create(color_input).graphql_type()

        @strawchemy.field(graphql_type=ColorType, arguments=data_argument(ColorCreateInput))
        def create_color_for_existing_fruits(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
            color_input = Input(data)
            session = cast("Session", info.context.session)
            apple, strawberry = (
                Fruit(name="New Apple", sweetness=1, water_percent=0.4),
                Fruit(name="New Strawberry", sweetness=1, water_percent=0.3),
            )
            session.add_all([apple, strawberry])
            session.commit()
            session.expire(strawberry)
            color_input.instances[0].fruits.extend([apple, strawberry])
            return StrawchemySyncRepository(ColorType, info).create(color_input).graphql_type()

        @strawchemy.field(graphql_type=FruitType, arguments=data_argument(FruitCreateInput))
        def create_red_fruit(self, info: strawberry.Info, data: FruitCreateInput) -> FruitType:
            fruit_input = Input(data)
            fruit_input.instances[0].color = Color(name="New Red")
            return StrawchemySyncRepository(FruitType, info).create(fruit_input).graphql_type()

        @strawchemy.field(graphql_type=FruitType, arguments=data_argument(FruitCreateInput))
        def create_fruit_for_existing_color(self, info: strawberry.Info, data: FruitCreateInput) -> FruitType:
            fruit_input = Input(data)
            session = cast("Session", info.context.session)
            red = Color(name="New Red")
            session.add(red)
            session.commit()
            fruit_input.instances[0].color = red
            return StrawchemySyncRepository(FruitType, info).create(fruit_input).graphql_type()

    is_async = issubclass(strawchemy.config.repository_type, StrawchemyAsyncRepository)
    return Operations(query=Query, mutation=AsyncMutation if is_async else SyncMutation)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.mark.snapshot
async def test_column_override(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
        mutation {
            createBlueColor(data: { name: "New Green" }) {
                name
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createBlueColor"] == {"name": "New Blue"}
    query_tracker.assert_statements(1, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.parametrize(
    ("query_name", "query"),
    [
        pytest.param(
            "createAppleColor",
            """
                mutation {
                    createAppleColor(data: { name: "Apple Red" }) {
                        name
                        fruits {
                            name
                        }
                    }
                }
                """,
            id="not-existing",
        ),
        pytest.param(
            "createColorForExistingFruits",
            """
                mutation {
                    createColorForExistingFruits(data: { name: "Apple Red" }) {
                        name
                        fruits {
                            name
                        }
                    }
                }
                """,
            id="existing",
        ),
    ],
)
async def test_relationship_to_many_override(query_name: str, query: str, any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data[query_name] == {
        "name": "Apple Red",
        "fruits": [{"name": "New Apple"}, {"name": "New Strawberry"}],
    }


@pytest.mark.parametrize(
    ("query_name", "query"),
    [
        pytest.param(
            "createRedFruit",
            """
            mutation {
                createRedFruit(data: { name: "New Apple", sweetness: 1, waterPercent: 0.1 }) {
                    name
                    color {
                        name
                    }
                }
            }
            """,
            id="not-existing",
        ),
        pytest.param(
            "createFruitForExistingColor",
            """
            mutation {
                createFruitForExistingColor(data: { name: "New Apple", sweetness: 1, waterPercent: 0.1 }) {
                    name
                    color {
                        name
                    }
                }
            }
            """,
            id="existing",
        ),
    ],
)
async def test_relationship_to_one_override(query_name: str, query: str, any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data[query_name] == {"name": "New Apple", "color": {"name": "New Red"}}


@pytest.mark.expire_on_commit
async def test_relationship_to_one_override_expired(any_query: AnyQueryExecutor) -> None:
    """Test that a to-one override connects when the session expired the related instance."""
    result = await maybe_async(
        any_query(
            """
            mutation {
                createFruitForExistingColor(data: { name: "New Apple", sweetness: 1, waterPercent: 0.1 }) {
                    name
                    color {
                        name
                    }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    assert result.data["createFruitForExistingColor"] == {"name": "New Apple", "color": {"name": "New Red"}}
