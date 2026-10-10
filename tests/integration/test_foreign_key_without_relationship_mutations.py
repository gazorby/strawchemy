from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import ForeignKey, Insert, MetaData, Text, insert, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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


class Fruit(_Base):
    __tablename__ = "fk_fruit"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)


class FruitLabel(_Base):
    __tablename__ = "fk_fruit_label"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    fruit_id: Mapped[int] = mapped_column(ForeignKey("fk_fruit.id"))
    name: Mapped[str] = mapped_column(Text)


@cache
def _schema_types(dialect: SupportedDialect) -> dict[str, type[Any]]:
    strawchemy = Strawchemy(dialect)

    @strawchemy.type(FruitLabel, include="all")
    class FruitLabelType: ...

    @strawchemy.create_input(FruitLabel, include="all")
    class FruitLabelCreate: ...

    @strawberry.type
    class AsyncQuery:
        fruit_labels: list[FruitLabelType] = strawchemy.field(repository_type=StrawchemyAsyncRepository)

    @strawberry.type
    class SyncQuery:
        fruit_labels: list[FruitLabelType] = strawchemy.field(repository_type=StrawchemySyncRepository)

    @strawberry.type
    class AsyncMutation:
        create_fruit_label: FruitLabelType = strawchemy.create(
            FruitLabelCreate, repository_type=StrawchemyAsyncRepository
        )

    @strawberry.type
    class SyncMutation:
        create_fruit_label: FruitLabelType = strawchemy.create(
            FruitLabelCreate, repository_type=StrawchemySyncRepository
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
    return [insert(Fruit).values([{"id": 1}, {"id": 2}])]


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


async def test_create_sets_foreign_key_without_relationship(
    any_query: AnyQueryExecutor, any_session: AnySession
) -> None:
    """Test that a create mutation sets a foreign key column no relationship covers."""
    result = await maybe_async(
        any_query(
            """
            mutation {
                createFruitLabel(data: { id: 1, fruitId: 2, name: "organic" }) {
                    id
                    fruitId
                    name
                }
            }
            """
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["createFruitLabel"] == {"id": 1, "fruitId": 2, "name": "organic"}
    rows = await maybe_async(any_session.execute(select(FruitLabel.id, FruitLabel.fruit_id, FruitLabel.name)))
    assert [tuple(row) for row in rows] == [(1, 2, "organic")]
