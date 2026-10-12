from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import strawberry
from sqlalchemy import ForeignKey, Insert, MetaData, Text, insert, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tests.integration.fixtures import Operations, SchemaTypes
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy import Strawchemy
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


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(FruitLabel, include=["id", "fruit_id", "name"])
    class FruitLabelType: ...

    @strawchemy.create_input(FruitLabel, include=["id", "fruit_id", "name"])
    class FruitLabelCreate: ...

    @strawberry.type
    class Query:
        fruit_labels: list[FruitLabelType] = strawchemy.field()

    @strawberry.type
    class Mutation:
        create_fruit_label: FruitLabelType = strawchemy.create(FruitLabelCreate)

    return Operations(query=Query, mutation=Mutation)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def metadata() -> MetaData:
    return _metadata


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Fruit).values([{"id": 1}, {"id": 2}])]


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
