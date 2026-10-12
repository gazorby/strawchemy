from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import Insert, insert
from strawberry.extensions.field_extension import FieldExtension
from typing_extensions import override

from strawchemy import ModelInstance
from tests.integration.fixtures import Operations, SchemaTypes
from tests.integration.models import Color, Fruit
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

_COLORS: list[dict[str, Any]] = [{"id": 1, "name": "Red"}]
_FRUITS: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "Apple",
        "sweetness": 4,
        "water_percent": 0.84,
        "best_time_to_pick": time(hour=9),
        "color_id": 1,
    },
    {
        "id": 2,
        "name": "Cherry",
        "sweetness": 9,
        "water_percent": 0.93,
        "best_time_to_pick": time(hour=10, minute=30),
        "color_id": 1,
    },
]


class _SomeExtension(FieldExtension):
    @override
    async def resolve_async(
        self, next_: Callable[..., Awaitable[Any]], source: Any, info: strawberry.Info, **kwargs: Any
    ) -> Any:
        fruit = await next_(source, info, **kwargs)
        assert fruit.instance.name == "Apple"
        return fruit

    @override
    def resolve(self, next_: Callable[..., Any], source: Any, info: strawberry.Info, **kwargs: Any) -> Any:
        fruit = next_(source, info, **kwargs)
        assert fruit.instance.name == "Apple"
        return fruit


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Fruit, include=["id", "name"])
    class FruitTypeHooks:
        instance: ModelInstance[Fruit]

    @strawberry.type
    class Query:
        fruit_with_extension: FruitTypeHooks = strawchemy.field(extensions=[_SomeExtension()])

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS), insert(Fruit).values(_FRUITS)]


async def test_field_extension(any_async_query: AnyQueryExecutor) -> None:
    result = await maybe_async(
        any_async_query(
            """
            query fruitWithExtension($id: Int!) {
                fruitWithExtension(id: $id) {
                    name
            }
            }
            """,
            {"id": _FRUITS[0]["id"]},
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["fruitWithExtension"] == {"name": _FRUITS[0]["name"]}
