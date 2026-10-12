from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import strawberry

from tests.integration.fixtures import Operations, SchemaTypes
from tests.integration.models import Color
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Color, include=["id", "name"])
    class ColorType: ...

    @strawchemy.create_input(Color, include=["id", "name"])
    class ColorCreateInput: ...

    @strawchemy.pk_update_input(Color, include=["id", "name"])
    class ColorUpdateInput: ...

    @strawchemy.filter(Color, include=["id"])
    class ColorFilter: ...

    @strawberry.type
    class Query:
        color: ColorType = strawchemy.field()
        colors: list[ColorType] = strawchemy.field(filter_input=ColorFilter)

    @strawberry.type
    class Mutation:
        create_color: ColorType = strawchemy.create(ColorCreateInput)
        update_color: ColorType = strawchemy.update_by_ids(ColorUpdateInput)
        delete_color: list[ColorType] = strawchemy.delete(ColorFilter)

    return Operations(query=Query, mutation=Mutation)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


async def test_create_update_delete(any_query: AnyQueryExecutor) -> None:
    color_id = 99999

    create_query = """
        mutation {{
            createColor(data: {{ id: {id}, name: "New Blue" }}) {{
                name
            }}
        }}
    """

    update_query = """
        mutation {{
            updateColor(
                data: {{
                    id: {id},
                    name: "New Green"
                }}
            ) {{
                id
                name
            }}
        }}
    """

    get_query = """
        query {{
            color(id: {id}) {{
                name
            }}
        }}
    """

    delete_query = """
        mutation {{
            deleteColor(
                filter: {{
                    id: {{ eq: {id} }}
                }}
            ) {{
                id
                name
            }}
        }}
    """

    list_query = """
        query {{
            colors(filter: {{ id: {{ eq: {id} }} }}) {{
                id
                name
            }}
        }}
    """

    # Create
    result = await maybe_async(any_query(create_query.format(id=color_id)))
    assert not result.errors
    assert result.data
    assert result.data["createColor"] == {"name": "New Blue"}
    # Get
    result = await maybe_async(any_query(get_query.format(id=color_id)))
    assert not result.errors
    assert result.data
    assert result.data["color"] == {"name": "New Blue"}
    # Update
    result = await maybe_async(any_query(update_query.format(id=color_id)))
    assert not result.errors
    assert result.data
    assert result.data["updateColor"] == {"name": "New Green", "id": color_id}
    # Get
    result = await maybe_async(any_query(get_query.format(id=color_id)))
    assert not result.errors
    assert result.data
    assert result.data["color"] == {"name": "New Green"}
    # Delete
    result = await maybe_async(any_query(delete_query.format(id=color_id)))
    assert not result.errors
    assert result.data
    assert result.data["deleteColor"] == [{"name": "New Green", "id": color_id}]
    # List
    result = await maybe_async(any_query(list_query.format(id=color_id)))
    assert not result.errors
    assert result.data
    assert result.data["colors"] == []
