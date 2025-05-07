from __future__ import annotations

from typing import Any

import pytest

_PYTEST_ARGS = "-p no:pretty"  # pretty plugin makes pytester unable to parse pytest output


@pytest.fixture(autouse=True)
def fx_pyproject(pytester: pytest.Pytester) -> None:
    pytester.makepyprojecttoml(
        """
        [tool.pytest.ini_options]
        asyncio_mode = "auto"
        asyncio_default_fixture_loop_scope = "function"
        """
    )


@pytest.mark.parametrize(
    ("query"),
    [
        pytest.param("{ fruits { name sweetness } }", id="basic"),
        pytest.param("{ fruits { name color { id name } } }", id="relation"),
    ],
)
def test_patch_query_fixture(query: str, pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        f"""
        import pytest
        import strawberry
        from strawchemy import Strawchemy, StrawchemyAsyncRepository, StrawchemySyncRepository, StrawchemyConfig
        from strawchemy.testing import MockContext
        from tests.unit.models import Fruit, SQLDataTypes
        from strawberry.scalars import JSON
        from typing import Any
        from datetime import timedelta
        from strawchemy.strawberry.scalars import Interval

        SCALAR_OVERRIDES: dict[object, Any] = {{dict[str, Any]: JSON, timedelta: Interval}}
        pytest_plugins = ["strawchemy.testing.pytest_plugin", "pytest_asyncio"]

        strawchemy = Strawchemy("postgresql")

        @strawchemy.type(Fruit, include="all")
        class FruitType:
            ...

        @strawchemy.type(SQLDataTypes, include="all")
        class DataTypes:
            ...

        @strawberry.type
        class QueryAsync:
            fruits: list[FruitType] = strawchemy.field(repository_type=StrawchemyAsyncRepository)
            data_types: list[DataTypes] = strawchemy.field(repository_type=StrawchemyAsyncRepository)

        @strawberry.type
        class QuerySync:
            fruits: list[FruitType] = strawchemy.field(repository_type=StrawchemySyncRepository)
            data_types: list[DataTypes] = strawchemy.field(repository_type=StrawchemySyncRepository)

        async def test_async(context: MockContext) -> None:
            schema = strawberry.Schema(query=QueryAsync, scalar_overrides=SCALAR_OVERRIDES)
            result = await schema.execute("{query}", context_value=context)
            assert result.errors is None
            assert result.data is not None

        def test_sync(context: MockContext) -> None:
            schema = strawberry.Schema(query=QuerySync, scalar_overrides=SCALAR_OVERRIDES)
            result = schema.execute_sync("{query}", context_value=context)
            assert result.errors is None
            assert result.data is not None
        """
    )

    result = pytester.runpytest(_PYTEST_ARGS)
    result.assert_outcomes(passed=2)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param(
            '"{ fruitsAggregate { aggregations { count } } }"',
            {"fruitsAggregate": {"aggregations": {"count": 0}}},
            id="root-aggregations",
        ),
        pytest.param(
            '"{ colors { fruitsAggregate { count } } }"',
            {"colors": [{"fruitsAggregate": {"count": 0}}]},
            id="child-aggregate-list",
        ),
        pytest.param(
            "'{ color(id: \"84552ccd-efad-4561-ac72-23ec5c5c2cf9\") { fruitsAggregate { count } } }'",
            {"color": {"fruitsAggregate": {"count": 0}}},
            id="child-aggregate-one",
        ),
    ],
)
def test_computed_values(query: str, expected: str, pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        f"""
        import pytest
        import strawberry
        from strawchemy import Strawchemy, StrawchemyConfig
        from strawchemy.testing import MockContext
        from tests.unit.models import Fruit, Color

        pytest_plugins = ["strawchemy.testing.pytest_plugin"]

        strawchemy = Strawchemy("postgresql")

        @strawchemy.aggregate(Fruit, include="all")
        class FruitAggregateType:
            pass

        @strawchemy.type(Color, include="all", override=True)
        class ColorType:
            pass

        @strawberry.type
        class Query:
            fruits_aggregate: FruitAggregateType = strawchemy.field(root_aggregations=True)
            colors: list[ColorType] = strawchemy.field()
            color: ColorType = strawchemy.field()

        def test(context: MockContext) -> None:
            schema = strawberry.Schema(query=Query)
            result = schema.execute_sync({query}, context_value=context)
            assert result.errors is None
            assert result.data is not None

            assert result.data == {expected}
        """
    )

    result = pytester.runpytest(_PYTEST_ARGS)
    result.assert_outcomes(passed=1)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param(
            '"{ fruitsAggregate { aggregations { count } } }"',
            {"fruitsAggregate": {"aggregations": {"count": 2}}},
            id="root-aggregations",
        ),
        pytest.param(
            '"{ colors { fruitsAggregate { count } } }"',
            {"colors": [{"fruitsAggregate": {"count": 2}}]},
            id="child-aggregate-list",
        ),
        pytest.param(
            "'{ color(id: \"84552ccd-efad-4561-ac72-23ec5c5c2cf9\") { fruitsAggregate { count } } }'",
            {"color": {"fruitsAggregate": {"count": 2}}},
            id="child-aggregate-one",
        ),
    ],
)
def test_custom_computed_values(query: str, expected: Any, pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        f"""
        from __future__ import annotations
        from typing import Any
        import pytest
        import strawberry
        from strawchemy import Strawchemy, StrawchemyConfig
        from strawchemy.testing import MockContext
        from tests.unit.models import Fruit, Color

        pytest_plugins = ["strawchemy.testing.pytest_plugin"]

        strawchemy = Strawchemy("postgresql")

        @strawchemy.aggregate(Fruit, include="all")
        class FruitAggregateType:
            pass

        @strawchemy.type(Color, include="all", override=True)
        class ColorType:
            pass

        @strawberry.type
        class Query:
            fruits_aggregate: FruitAggregateType = strawchemy.field(root_aggregations=True)
            colors: list[ColorType] = strawchemy.field()
            color: ColorType = strawchemy.field()

        @pytest.fixture
        def computed_values() -> dict[str, Any]:
            return {{"count": 2}}

        def test(context: MockContext) -> None:
            schema = strawberry.Schema(query=Query)
            result = schema.execute_sync({query}, context_value=context)
            assert result.errors is None
            assert result.data is not None

            assert result.data == {expected}
        """
    )

    result = pytester.runpytest(_PYTEST_ARGS)
    result.assert_outcomes(passed=1)
