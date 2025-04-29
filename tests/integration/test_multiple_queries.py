from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest
from strawchemy import Input, StrawchemyAsyncRepository, StrawchemySyncRepository, ValidationErrorType

import strawberry
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from tests.integration.models import Fruit
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .types import (
    ColorCreateInput,
    ColorCreateValidation,
    ColorFilter,
    ColorPartial,
    ColorPkUpdateValidation,
    ColorType,
    ColorUpdateInput,
    strawchemy,
)

pytestmark = [pytest.mark.integration]


@strawberry.type
class AsyncQuery:
    colors: list[ColorType] = strawchemy.field(filter_input=ColorFilter, repository_type=StrawchemyAsyncRepository)
    color: ColorType = strawchemy.field(filter_input=ColorFilter, repository_type=StrawchemyAsyncRepository)


@strawberry.type
class SyncQuery:
    colors: list[ColorType] = strawchemy.field(filter_input=ColorFilter, repository_type=StrawchemySyncRepository)
    color: ColorType = strawchemy.field(filter_input=ColorFilter, repository_type=StrawchemySyncRepository)


@strawberry.type
class AsyncMutation:
    # Create
    create_color: ColorType = strawchemy.create(ColorCreateInput, repository_type=StrawchemyAsyncRepository)
    create_validated_color: ColorType | ValidationErrorType = strawchemy.create(
        ColorCreateInput, validation=ColorCreateValidation, repository_type=StrawchemyAsyncRepository
    )
    create_colors: list[ColorType] = strawchemy.create(ColorCreateInput, repository_type=StrawchemyAsyncRepository)

    # Update
    update_color: ColorType = strawchemy.update_by_ids(ColorUpdateInput, repository_type=StrawchemyAsyncRepository)
    update_colors: list[ColorType] = strawchemy.update_by_ids(
        ColorUpdateInput, repository_type=StrawchemyAsyncRepository
    )
    update_validated_color: ColorType | ValidationErrorType = strawchemy.update_by_ids(
        ColorUpdateInput, validation=ColorPkUpdateValidation, repository_type=StrawchemyAsyncRepository
    )
    update_colors_filter: list[ColorType] = strawchemy.update(
        ColorPartial, ColorFilter, repository_type=StrawchemyAsyncRepository
    )
    # Delete
    delete_color: list[ColorType] = strawchemy.delete(ColorFilter, repository_type=StrawchemyAsyncRepository)
    delete_colors: list[ColorType] = strawchemy.delete(ColorFilter, repository_type=StrawchemyAsyncRepository)

    @strawberry.field
    async def create_apple_color(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
        color_input = Input(data)
        color_input.instances[0].fruits.extend([Fruit(name="Apple"), Fruit(name="Strawberry")])
        return await StrawchemyAsyncRepository(ColorType, info).create(color_input)

    @strawberry.field
    async def create_color_for_existing_fruits(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
        color_input = Input(data)
        session = cast("AsyncSession", info.context.session)
        apple, strawberry = Fruit(name="Apple"), Fruit(name="Strawberry")
        session.add_all([apple, strawberry])
        await session.commit()
        session.expire(strawberry)
        color_input.instances[0].fruits.extend([apple, strawberry])
        return await StrawchemyAsyncRepository(ColorType, info).create(color_input)


@strawberry.type
class SyncMutation:
    # Create
    create_color: ColorType = strawchemy.create(ColorCreateInput, repository_type=StrawchemySyncRepository)
    create_validated_color: ColorType | ValidationErrorType = strawchemy.create(
        ColorCreateInput, validation=ColorCreateValidation, repository_type=StrawchemySyncRepository
    )
    create_colors: list[ColorType] = strawchemy.create(ColorCreateInput, repository_type=StrawchemySyncRepository)

    # Update
    update_color: ColorType = strawchemy.update_by_ids(ColorUpdateInput, repository_type=StrawchemySyncRepository)
    update_colors: list[ColorType] = strawchemy.update_by_ids(
        ColorUpdateInput, repository_type=StrawchemySyncRepository
    )
    update_validated_color: ColorType | ValidationErrorType = strawchemy.update_by_ids(
        ColorUpdateInput, validation=ColorPkUpdateValidation, repository_type=StrawchemySyncRepository
    )
    update_colors_filter: list[ColorType] = strawchemy.update(
        ColorPartial, ColorFilter, repository_type=StrawchemySyncRepository
    )
    # Delete
    delete_color: list[ColorType] = strawchemy.delete(ColorFilter, repository_type=StrawchemySyncRepository)
    delete_colors: list[ColorType] = strawchemy.delete(ColorFilter, repository_type=StrawchemySyncRepository)

    @strawberry.field
    def create_apple_color(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
        color_input = Input(data)
        color_input.instances[0].fruits.extend([Fruit(name="Apple"), Fruit(name="Strawberry")])
        return StrawchemySyncRepository(ColorType, info).create(color_input)

    @strawberry.field
    def create_color_for_existing_fruits(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
        color_input = Input(data)
        session = cast("Session", info.context.session)
        apple, strawberry = Fruit(name="Apple"), Fruit(name="Strawberry")
        session.add_all([apple, strawberry])
        session.commit()
        session.expire(strawberry)
        color_input.instances[0].fruits.extend([apple, strawberry])
        return StrawchemySyncRepository(ColorType, info).create(color_input)


@pytest.fixture
def sync_mutation() -> type[SyncMutation]:
    return SyncMutation


@pytest.fixture
def async_mutation() -> type[AsyncMutation]:
    return AsyncMutation


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery


async def test_create_update_delete(any_query: AnyQueryExecutor) -> None:
    color_id = str(uuid4())

    create_query = """
        mutation {{
            createColor(data: {{ id: "{id}", name: "Blue" }}) {{
                name
            }}
        }}
    """

    update_query = """
        mutation {{
            updateColor(
                data: {{
                    id: "{id}",
                    name: "Green"
                }}
            ) {{
                id
                name
            }}
        }}
    """

    get_query = """
        query {{
            color(id: "{id}") {{
                name
            }}
        }}
    """

    delete_query = """
        mutation {{
            deleteColor(
                filter: {{
                    id: {{ eq: "{id}" }}
                }}
            ) {{
                id
                name
            }}
        }}
    """

    list_query = """
        query {{
            colors(filter: {{ id: {{ eq: "{id}" }} }}) {{
                id
                name
            }}
        }}
    """

    # Create
    result = await maybe_async(any_query(create_query.format(id=color_id)))
    assert not result.errors
    assert result.data
    assert result.data["createColor"] == {"name": "Blue"}
    # Get
    result = await maybe_async(any_query(get_query.format(id=color_id)))
    assert not result.errors
    assert result.data
    assert result.data["color"] == {"name": "Blue"}
    # Update
    result = await maybe_async(any_query(update_query.format(id=color_id)))
    assert not result.errors
    assert result.data
    assert result.data["updateColor"] == {"name": "Green", "id": color_id}
    # Get
    result = await maybe_async(any_query(get_query.format(id=color_id)))
    assert not result.errors
    assert result.data
    assert result.data["color"] == {"name": "Green"}
    # Delete
    result = await maybe_async(any_query(delete_query.format(id=color_id)))
    assert not result.errors
    assert result.data
    assert result.data["deleteColor"] == [{"name": "Green", "id": color_id}]
    # List
    result = await maybe_async(any_query(list_query.format(id=color_id)))
    assert not result.errors
    assert result.data
    assert result.data["colors"] == []
