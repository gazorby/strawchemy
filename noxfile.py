from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import nox
from nox_uv import session

if TYPE_CHECKING:
    from nox import Session

SUPPORTED_PYTHON_VERSIONS = ["3.10", "3.11", "3.12", "3.13", "3.14"]
COMMON_PYTEST_OPTIONS = ["-n=2", "--showlocals", "-vv"]

here = Path(__file__).parent

nox.options.default_venv_backend = "uv"
nox.options.error_on_external_run = True
nox.options.error_on_missing_interpreters = True


@session(
    name="unit",
    python=SUPPORTED_PYTHON_VERSIONS,
    tags=["tests", "unit", "ci"],
    uv_groups=["test"],
    uv_all_extras=True,
    uv_sync_locked=False,
)
def unit_tests(session: Session) -> None:
    (here / ".coverage").unlink(missing_ok=True)
    args: list[str] = ["-m=not integration", "tests/unit", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args)


@session(
    name="unit-no-extras",
    python=SUPPORTED_PYTHON_VERSIONS,
    tags=["tests", "unit", "ci"],
    uv_groups=["test"],
    uv_all_extras=False,
    uv_sync_locked=False,
)
def unit_tests_no_extras(session: Session) -> None:
    (here / ".coverage").unlink(missing_ok=True)
    args: list[str] = ["-m=not integration", "tests/unit", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args)


@session(
    name="integration",
    python=SUPPORTED_PYTHON_VERSIONS,
    tags=["tests", "docker", "integration"],
    uv_groups=["test"],
    uv_all_extras=True,
    uv_sync_locked=False,
)
def integration_tests(session: Session) -> None:
    (here / ".coverage").unlink(missing_ok=True)
    args: list[str] = ["-m=integration", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args)


@session(
    name="integration-postgres",
    python=SUPPORTED_PYTHON_VERSIONS,
    tags=["tests", "docker", "integration", "ci", "postgres"],
    uv_groups=["test"],
    uv_all_extras=True,
    uv_sync_locked=False,
)
def integration_postgres_tests(session: Session) -> None:
    (here / ".coverage").unlink(missing_ok=True)
    args: list[str] = ["-m=asyncpg or psycopg_async or psycopg_sync", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args)


@session(
    name="integration-mysql",
    python=SUPPORTED_PYTHON_VERSIONS,
    tags=["tests", "docker", "integration", "ci", "mysql"],
    uv_groups=["test"],
    uv_all_extras=True,
    uv_sync_locked=False,
)
def integration_mysql_tests(session: Session) -> None:
    (here / ".coverage").unlink(missing_ok=True)
    args: list[str] = ["-m=asyncmy", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args)


@session(
    name="integration-sqlite",
    python=SUPPORTED_PYTHON_VERSIONS,
    tags=["tests", "docker", "integration", "ci", "sqlite"],
    uv_groups=["test"],
    uv_all_extras=True,
    uv_sync_locked=False,
)
def integration_sqlite_tests(session: Session) -> None:
    (here / ".coverage").unlink(missing_ok=True)
    args: list[str] = ["-m aiosqlite or sqlite", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args)
