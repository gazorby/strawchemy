from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import ForeignKey, Insert, MetaData, String, Text, insert, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from strawchemy import Strawchemy, StrawchemyAsyncRepository, StrawchemySyncRepository
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy.repository.typing import AnySession
    from strawchemy.typing import SupportedDialect
    from tests.typing import AnyQueryExecutor

pytestmark = [pytest.mark.integration]

_metadata = MetaData()


class _Base(DeclarativeBase):
    metadata = _metadata


class Basket(_Base):
    __tablename__ = "pk_filter_basket"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)


class BasketItem(_Base):
    __tablename__ = "pk_filter_basket_item"

    basket_id: Mapped[int] = mapped_column(ForeignKey("pk_filter_basket.id"), primary_key=True)
    label: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    basket: Mapped[Basket] = relationship(Basket)


@cache
def _schema_types(dialect: SupportedDialect) -> dict[str, type[Any]]:
    strawchemy = Strawchemy(dialect)

    @strawchemy.type(BasketItem, include="all")
    class BasketItemType: ...

    @strawchemy.filter_update_input(BasketItem, include="all")
    class BasketItemPartial: ...

    @strawchemy.filter(BasketItem, include="all")
    class BasketItemFilter: ...

    @strawberry.type
    class AsyncQuery:
        basket_items: list[BasketItemType] = strawchemy.field(repository_type=StrawchemyAsyncRepository)

    @strawberry.type
    class SyncQuery:
        basket_items: list[BasketItemType] = strawchemy.field(repository_type=StrawchemySyncRepository)

    @strawberry.type
    class AsyncMutation:
        update_basket_items: list[BasketItemType] = strawchemy.update(
            BasketItemPartial, BasketItemFilter, repository_type=StrawchemyAsyncRepository
        )

    @strawberry.type
    class SyncMutation:
        update_basket_items: list[BasketItemType] = strawchemy.update(
            BasketItemPartial, BasketItemFilter, repository_type=StrawchemySyncRepository
        )

    return {
        "async_query": AsyncQuery,
        "sync_query": SyncQuery,
        "async_mutation": AsyncMutation,
        "sync_mutation": SyncMutation,
    }


@pytest.fixture
def metadata() -> MetaData:
    return _metadata


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [
        insert(Basket).values([{"id": 1}, {"id": 2}]),
        insert(BasketItem).values(
            [
                {"basket_id": 1, "label": "fruit", "name": "apple"},
                {"basket_id": 1, "label": "veggie", "name": "leek"},
                {"basket_id": 2, "label": "fruit", "name": "pear"},
            ]
        ),
    ]


@pytest.fixture
def async_query(dialect: SupportedDialect) -> type[Any]:
    return _schema_types(dialect)["async_query"]


@pytest.fixture
def sync_query(dialect: SupportedDialect) -> type[Any]:
    return _schema_types(dialect)["sync_query"]


@pytest.fixture
def async_mutation(dialect: SupportedDialect) -> type[Any]:
    return _schema_types(dialect)["async_mutation"]


@pytest.fixture
def sync_mutation(dialect: SupportedDialect) -> type[Any]:
    return _schema_types(dialect)["sync_mutation"]


@pytest.mark.parametrize(
    ("data", "filter_", "expected", "expected_table"),
    [
        pytest.param(
            '{ name: "renamed", label: "dessert" }',
            '{ label: { eq: "fruit" } }',
            [
                {"basketId": 1, "label": "dessert", "name": "renamed"},
                {"basketId": 2, "label": "dessert", "name": "renamed"},
            ],
            [(1, "dessert", "renamed"), (1, "veggie", "leek"), (2, "dessert", "renamed")],
            id="key-column-set-directly",
        ),
        pytest.param(
            '{ name: "moved", basket: { set: { id: 2 } } }',
            '{ label: { eq: "veggie" } }',
            [{"basketId": 2, "label": "veggie", "name": "moved"}],
            [(1, "fruit", "apple"), (2, "fruit", "pear"), (2, "veggie", "moved")],
            id="key-column-set-through-relation",
        ),
        pytest.param(
            '{ name: "plum" }',
            '{ label: { eq: "fruit" } }',
            [{"basketId": 1, "label": "fruit", "name": "plum"}, {"basketId": 2, "label": "fruit", "name": "plum"}],
            [(1, "fruit", "plum"), (1, "veggie", "leek"), (2, "fruit", "plum")],
            id="non-key-column",
        ),
    ],
)
async def test_filter_update_returns_rows_under_their_new_key(
    data: str,
    filter_: str,
    expected: list[dict[str, Any]],
    expected_table: list[tuple[Any, ...]],
    any_query: AnyQueryExecutor,
    any_session: AnySession,
) -> None:
    """Test that a filter update returns every updated row, including those whose primary key it changed."""
    result = await maybe_async(
        any_query(
            f"""
            mutation {{
                updateBasketItems(data: {data}, filter: {filter_}) {{
                    basketId
                    label
                    name
                }}
            }}
            """
        )
    )

    assert not result.errors
    assert result.data
    assert sorted(result.data["updateBasketItems"], key=lambda row: (row["basketId"], row["label"])) == expected

    rows = await maybe_async(
        any_session.execute(
            select(BasketItem.basket_id, BasketItem.label, BasketItem.name).order_by(
                BasketItem.basket_id, BasketItem.label
            )
        )
    )
    assert [tuple(row) for row in rows] == expected_table
