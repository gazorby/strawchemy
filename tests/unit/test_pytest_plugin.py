from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def test_patch_query_fixture_async(pytester: pytest.Pytester) -> None:
    pytester.makepyprojecttoml(
        """
        [tool.pytest.ini_options]
        asyncio_mode = "auto"
        asyncio_default_fixture_loop_scope = "function"
        """
    )
    pytester.makepyfile(
        """
        import pytest
        import strawberry
        from strawchemy import Strawchemy
        from tests.unit.models import Fruit

        pytest_plugins = ["strawchemy.testing.pytest_plugin", "pytest_asyncio"]

        strawchemy = Strawchemy()

        @strawchemy.type(Fruit, include="all")
        class FruitType:
            pass

        @strawberry.type
        class Query:
            fruits: list[FruitType] = strawchemy.field()

        async def test(context) -> None:
            schema = strawberry.Schema(query=Query)
            result = await schema.execute("{ fruits { name } }", context_value=context)
            assert result.errors is None
            assert result.data is not None
        """
    )

    result = pytester.runpytest("-p no:pretty")  # pretty plugin makes pytester unable to parse pytest output
    result.assert_outcomes(passed=1)


def test_patch_query_fixture_sync(pytester: pytest.Pytester) -> None:
    pytester.makepyprojecttoml(
        """
        [tool.pytest.ini_options]
        asyncio_mode = "auto"
        asyncio_default_fixture_loop_scope = "function"
        """
    )
    pytester.makepyfile(
        """
        import pytest
        import strawberry
        from strawchemy import Strawchemy
        from tests.unit.models import Fruit

        pytest_plugins = ["strawchemy.testing.pytest_plugin"]

        strawchemy = Strawchemy()

        @strawchemy.type(Fruit, include="all")
        class FruitType:
            pass

        @strawberry.type
        class Query:
            fruits: list[FruitType] = strawchemy.field()

        def test(context) -> None:
            schema = strawberry.Schema(query=Query)
            result = schema.execute_sync("{ fruits { name } }", context_value=context)
            assert result.errors is None
            assert result.data is not None
        """
    )

    result = pytester.runpytest("-p no:pretty")  # pretty plugin makes pytester unable to parse pytest output
    result.assert_outcomes(passed=1)
