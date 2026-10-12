from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import strawberry
from sqlalchemy.ext.asyncio import AsyncSession

from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository
from tests.integration.fixtures import Operations, SchemaTypes
from tests.integration.models import Color

if TYPE_CHECKING:
    from strawchemy import Strawchemy, StrawchemyConfig
    from strawchemy.repository.typing import AnySession
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]


def _color_schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Color, include=["id", "name"])
    class ColorType: ...

    @strawberry.type
    class Query:
        colors: list[ColorType] = strawchemy.field()

    return Operations(query=Query)


def _other_color_schema(strawchemy: Strawchemy) -> Operations:
    return _color_schema(strawchemy)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _color_schema)


def test_schema_types_build_is_cached_per_builder() -> None:
    """Two builders on one dialect get distinct schemas, and one builder always gets the same one."""
    assert SchemaTypes.build("sqlite", _color_schema) is SchemaTypes.build("sqlite", _color_schema)
    assert SchemaTypes.build("sqlite", _color_schema) is not SchemaTypes.build("sqlite", _other_color_schema)


def test_schema_types_build_uses_repository_per_mapper() -> None:
    """Building a schema configures each mapper with its repository and runs the builder on both."""
    seen: list[Strawchemy] = []

    def builder(strawchemy: Strawchemy) -> Operations:
        seen.append(strawchemy)
        return _color_schema(strawchemy)

    types = SchemaTypes.build("sqlite", builder)

    assert types.async_mapper.config.repository_type is StrawchemyAsyncRepository
    assert types.sync_mapper.config.repository_type is StrawchemySyncRepository
    assert seen == [types.async_mapper, types.sync_mapper]


def test_config_fixture_returns_session_mapper_config(
    any_session: AnySession, config: StrawchemyConfig, schema: SchemaTypes
) -> None:
    """The config fixture is the config of the mapper matching the running session."""
    expected = schema.async_mapper if isinstance(any_session, AsyncSession) else schema.sync_mapper
    assert config is expected.config


def test_default_schema_fixture_fails_without_override(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A module requesting a query without overriding the schema fixture fails naming the module."""
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parents[2]))
    pytester.makepyprojecttoml('[tool.pytest.ini_options]\nasyncio_mode = "auto"\n')
    pytester.makeconftest("from tests.integration.conftest import *  # noqa: F403\n")
    pytester.makepyfile(
        test_missing_schema="""
        import pytest

        pytestmark = [pytest.mark.integration]


        def test_query(any_query):
            ...
        """
    )

    result = pytester.runpytest_subprocess(
        "-p", "no:pretty", "-p", "no:pytest_databases", "-k", "sqlite", "-W", "ignore::pytest.PytestUnknownMarkWarning"
    )

    assert result.parseoutcomes().get("errors", 0) > 0
    result.stdout.fnmatch_lines(["*test_missing_schema must override the schema fixture*"])
