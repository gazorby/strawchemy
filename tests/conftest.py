from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pytest_databases._service import DockerService
from typing_extensions import Self

from tests.fixtures import fx_sqlalchemy_pydantic_factory, graphql_snapshot, sql_snapshot, strawchemy, sync_query

if TYPE_CHECKING:
    from collections.abc import Generator

    from docker import DockerClient
    from pytest_databases.types import ServiceContainer

pytest_plugins = ("pytest_databases.docker.postgres", "pytest_databases.docker.mysql", "pytester")

__all__ = ("fx_sqlalchemy_pydantic_factory", "graphql_snapshot", "sql_snapshot", "strawchemy", "sync_query")

EXTRAS_ENV_VAR = "STRAWCHEMY_TEST_EXTRAS"

_EXTRA_MODULES = {"geo": ("geoalchemy2", "geojson_pydantic", "shapely"), "pydantic": ("pydantic",)}

# ``DockerService`` locks on ``<tmp_path>/<container name>`` before creating a container. The path pytest
# hands out is unique to the session, so two checkouts starting at once both try to create the container
# and one gets a 409 from the daemon. A machine-wide directory makes that lock do its job across sessions.
_CONTAINER_LOCK_DIR = Path(tempfile.gettempdir()) / "strawchemy-pytest-databases"

# Ten seconds, the default, is not enough for a container to accept connections when two checkouts
# boot their servers at the same time.
_CONTAINER_READY_TIMEOUT = 60


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


class _PersistentDockerService(DockerService):
    """Docker service that leaves alone the containers it did not start."""

    # The base class kills every container carrying the ``pytest_databases`` label both when a
    # session opens and when it closes, tearing down the databases of any run happening in another
    # checkout. Not entering also leaves the control file absent, which is what the
    # ``pytest_sessionfinish`` teardown of ``pytest_databases`` keys on.

    def __enter__(self) -> Self:
        return self

    def _stop_all_containers(self) -> None:
        pass

    @contextmanager
    def run(self, *args: Any, **kwargs: Any) -> Generator[ServiceContainer]:
        kwargs.setdefault("timeout", _CONTAINER_READY_TIMEOUT)
        with super().run(*args, **kwargs) as service:
            yield service


@pytest.fixture(scope="session")
def docker_service(docker_client: DockerClient, request: pytest.FixtureRequest) -> Generator[DockerService]:
    _CONTAINER_LOCK_DIR.mkdir(exist_ok=True)
    with _PersistentDockerService(
        client=docker_client, tmp_path=_CONTAINER_LOCK_DIR, session=request.session
    ) as service:
        yield service
