from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import Insert, insert

from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import Color
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

_COLORS: list[dict[str, Any]] = [{"id": 1, "name": "Red"}, {"id": 2, "name": "Green"}]
_EXECUTION_OPTIONS = {"strawchemy_test_marker": True}


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Color, include=["id", "name"], override=True)
    class ColorType: ...

    @strawchemy.create_input(Color, include="all")
    class ColorCreateInput: ...

    @strawchemy.pk_update_input(Color, include=["id", "name"])
    class ColorUpdateInput: ...

    @strawchemy.filter_update_input(Color, include=["name"])
    class ColorPartial: ...

    @strawchemy.filter(Color, include=["id", "name"])
    class ColorFilter: ...

    @strawchemy.upsert_update_fields(Color, include=["name"])
    class ColorUpsertFields: ...

    @strawchemy.upsert_conflict_fields(Color, include=["id"])
    class ColorConflictFields: ...

    @strawberry.type
    class Query:
        colors: list[ColorType] = strawchemy.field()

    @strawberry.type
    class Mutation:
        create_color: ColorType = strawchemy.create(ColorCreateInput, execution_options=_EXECUTION_OPTIONS)
        upsert_color: ColorType = strawchemy.upsert(
            ColorCreateInput,
            update_fields=ColorUpsertFields,
            conflict_fields=ColorConflictFields,
            execution_options=_EXECUTION_OPTIONS,
        )
        update_color: ColorType = strawchemy.update_by_ids(ColorUpdateInput, execution_options=_EXECUTION_OPTIONS)
        update_colors: list[ColorType] = strawchemy.update(
            ColorPartial, ColorFilter, execution_options=_EXECUTION_OPTIONS
        )
        delete_colors: list[ColorType] = strawchemy.delete(ColorFilter, execution_options=_EXECUTION_OPTIONS)
        delete_colors_default: list[ColorType] = strawchemy.delete(ColorFilter)

    return Operations(query=Query, mutation=Mutation)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS)]


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param('createColor(data: { name: "Blue" })', id="create"),
        pytest.param(
            'upsertColor(data: { id: 1, name: "Blue" }, conflictFields: id, updateFields: [name])', id="upsert"
        ),
        pytest.param('updateColor(data: { id: 1, name: "Blue" })', id="update_by_ids"),
        pytest.param('updateColors(data: { name: "Blue" }, filter: { id: { eq: 1 } })', id="update"),
        pytest.param("deleteColors(filter: { id: { eq: 1 } })", id="delete"),
    ],
)
async def test_mutation_execution_options(
    mutation: str, any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that a mutation's `execution_options` reach the query selecting the rows it returns."""
    result = await maybe_async(any_async_query(f"mutation {{ {mutation} {{ id }} }}"))
    assert not result.errors

    assert any(
        execution.execution_options.items() >= _EXECUTION_OPTIONS.items()
        for execution in query_tracker.filter("select").executions
    )


async def test_mutation_without_execution_options(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that a mutation declared without `execution_options` selects its rows without them."""
    result = await maybe_async(any_async_query("mutation { deleteColorsDefault(filter: { id: { eq: 1 } }) { id } }"))
    assert not result.errors

    assert query_tracker.filter("select").executions
    assert not any(
        "strawchemy_test_marker" in execution.execution_options
        for execution in query_tracker.filter("select").executions
    )
