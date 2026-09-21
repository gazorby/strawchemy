from __future__ import annotations

import os
from importlib.util import find_spec

import pytest

from tests.fixtures import fx_sqlalchemy_pydantic_factory, graphql_snapshot, sql_snapshot, strawchemy, sync_query

pytest_plugins = ("pytest_databases.docker.postgres", "pytest_databases.docker.mysql", "pytester")

__all__ = ("fx_sqlalchemy_pydantic_factory", "graphql_snapshot", "sql_snapshot", "strawchemy", "sync_query")

EXTRAS_ENV_VAR = "STRAWCHEMY_TEST_EXTRAS"

_EXTRA_MODULES = {"geo": ("geoalchemy2", "geojson_pydantic", "shapely"), "pydantic": ("pydantic",)}


def pytest_configure() -> None:
    """Abort when the runner promised extras that aren't installed.

    Suites needing an extra skip themselves when it's missing, which would otherwise report
    green in a run meant to exercise them.
    """
    required = [extra for extra in os.environ.get(EXTRAS_ENV_VAR, "").split(",") if extra]
    if unknown := set(required) - _EXTRA_MODULES.keys():
        msg = f"{EXTRAS_ENV_VAR} names unknown extras: {', '.join(sorted(unknown))}"
        raise pytest.UsageError(msg)
    missing = [module for extra in required for module in _EXTRA_MODULES[extra] if find_spec(module) is None]
    if missing:
        msg = f"{EXTRAS_ENV_VAR}={','.join(required)}, but {', '.join(missing)} are not installed"
        raise pytest.UsageError(msg)
