from __future__ import annotations

from datetime import datetime  # noqa: TC003  # resolved at runtime by SQLAlchemy
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy import ForeignKey, MetaData, Text, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from tests.integration.fixtures import Operations, SchemaTypes
from tests.utils import maybe_async

if TYPE_CHECKING:
    from sqlalchemy import Insert

    from strawchemy import Strawchemy
    from strawchemy.repository.typing import AnySession
    from strawchemy.typing import SupportedDialect
    from tests.typing import AnyQueryExecutor

pytestmark = [pytest.mark.integration]

_metadata = MetaData()


class _Base(DeclarativeBase):
    metadata = _metadata


class Basket(_Base):
    __tablename__ = "generated_basket"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    items: Mapped[list[BasketItem]] = relationship("BasketItem", back_populates="basket")


class BasketItem(_Base):
    __tablename__ = "generated_basket_item"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    basket_id: Mapped[UUID] = mapped_column(ForeignKey("generated_basket.id"))
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    basket: Mapped[Basket] = relationship(Basket, back_populates="items")


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Basket, include="all")
    class BasketType: ...

    @strawchemy.create_input(Basket, include=["id", "name", "created_at", "items"])
    class BasketCreate: ...

    @strawberry.type
    class Query:
        baskets: list[BasketType] = strawchemy.field()

    @strawberry.type
    class Mutation:
        create_basket: BasketType = strawchemy.create(BasketCreate)

    return Operations(query=Query, mutation=Mutation)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def metadata() -> MetaData:
    return _metadata


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return []


async def test_create_omitting_generated_values_lets_database_generate_them(
    any_query: AnyQueryExecutor, any_session: AnySession
) -> None:
    """Test that a create input with an explicit include generates omitted keys and SQL defaults, nested included."""
    result = await maybe_async(
        any_query(
            """
            mutation {
                createBasket(data: { name: "basket", items: { create: [{ name: "apple" }, { name: "pear" }] } }) {
                    name
                    items {
                        name
                    }
                }
            }
            """
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["createBasket"]["name"] == "basket"
    assert sorted(item["name"] for item in result.data["createBasket"]["items"]) == ["apple", "pear"]
    baskets = (await maybe_async(any_session.execute(select(Basket.id, Basket.created_at)))).all()
    items = (await maybe_async(any_session.execute(select(BasketItem.id, BasketItem.created_at)))).all()
    assert len(baskets) == 1
    assert len(items) == 2
    assert all(row.id is not None and row.created_at is not None for row in [*baskets, *items])
    assert len({row.id for row in items}) == 2
