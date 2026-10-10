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
    from tests.integration.fixtures import QueryTracker
    from tests.typing import AnyQueryExecutor

pytestmark = [pytest.mark.integration]

_metadata = MetaData()


class _Base(DeclarativeBase):
    metadata = _metadata


class Basket(_Base):
    __tablename__ = "basket"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)


class BasketItem(_Base):
    __tablename__ = "basket_item"

    basket_id: Mapped[int] = mapped_column(ForeignKey("basket.id"), primary_key=True)
    label: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    basket: Mapped[Basket] = relationship(Basket)


@cache
def _schema_types(dialect: SupportedDialect) -> dict[str, type[Any]]:
    strawchemy = Strawchemy(dialect)

    @strawchemy.type(BasketItem, include="all")
    class BasketItemType: ...

    @strawchemy.pk_update_input(BasketItem, include="all")
    class BasketItemUpdate: ...

    @strawberry.type
    class AsyncQuery:
        basket_items: list[BasketItemType] = strawchemy.field(repository_type=StrawchemyAsyncRepository)

    @strawberry.type
    class SyncQuery:
        basket_items: list[BasketItemType] = strawchemy.field(repository_type=StrawchemySyncRepository)

    @strawberry.type
    class AsyncMutation:
        update_basket_item: BasketItemType = strawchemy.update_by_ids(
            BasketItemUpdate, repository_type=StrawchemyAsyncRepository
        )

    @strawberry.type
    class SyncMutation:
        update_basket_item: BasketItemType = strawchemy.update_by_ids(
            BasketItemUpdate, repository_type=StrawchemySyncRepository
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


async def test_update_by_ids_matches_every_key_column(
    any_query: AnyQueryExecutor, any_session: AnySession, query_tracker: QueryTracker
) -> None:
    """Test that update by ids on a key holding a foreign key only updates the row matching the whole key."""
    result = await maybe_async(
        any_query(
            """
            mutation {
                updateBasketItem(data: { basketId: 2, label: "fruit", name: "plum" }) {
                    basketId
                    label
                    name
                }
            }
            """
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["updateBasketItem"] == {"basketId": 2, "label": "fruit", "name": "plum"}
    query_tracker.assert_statements(1, "update")
    where_clause = query_tracker.filter("update")[0].statement_str.partition("WHERE")[2]
    assert "basket_item.basket_id = " in where_clause
    assert "basket_item.label = " in where_clause

    rows = await maybe_async(
        any_session.execute(select(BasketItem.basket_id, BasketItem.name).order_by(BasketItem.basket_id))
    )
    assert [tuple(row) for row in rows] == [(1, "apple"), (2, "plum")]


async def test_update_by_ids_cannot_rewrite_key_through_relation(
    any_query: AnyQueryExecutor, any_session: AnySession
) -> None:
    """Test that update by ids refuses a to-one relation write targeting a column of the identifying key."""
    result = await maybe_async(
        any_query(
            """
            mutation {
                updateBasketItem(
                    data: { basketId: 1, label: "fruit", name: "plum", basket: { set: { id: 2 } } }
                ) {
                    basketId
                    label
                    name
                }
            }
            """
        )
    )

    assert result.errors

    rows = await maybe_async(
        any_session.execute(select(BasketItem.basket_id, BasketItem.name).order_by(BasketItem.basket_id))
    )
    assert [tuple(row) for row in rows] == [(1, "apple"), (2, "pear")]
