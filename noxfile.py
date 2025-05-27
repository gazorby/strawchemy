from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import nox

if TYPE_CHECKING:
    from nox import Session

SUPPORTED_PYTHON_VERSIONS = ["3.9", "3.10", "3.11", "3.12", "3.13"]
COMMON_PYTEST_OPTIONS = ["-n=2", "--showlocals", "-vv"]

here = Path(__file__).parent


nox.options.error_on_external_run = True
nox.options.default_venv_backend = "uv"


@nox.session(name="unit", python=SUPPORTED_PYTHON_VERSIONS, tags=["tests", "unit", "ci"])
def unit_tests(session: Session) -> None:
    (here / ".coverage").unlink(missing_ok=True)
    session.run_install(
        "uv", "sync", "--all-extras", "--group=test", env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location}
    )
    args: list[str] = ["-m=not integration", "tests/unit", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args)


@nox.session(name="unit-no-extras", python=SUPPORTED_PYTHON_VERSIONS, tags=["tests", "unit", "ci"])
def unit_tests_no_extras(session: Session) -> None:
    (here / ".coverage").unlink(missing_ok=True)
    session.run_install("uv", "sync", "--group=test", env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location})
    args: list[str] = ["-m=not integration", "tests/unit", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args)


@nox.session(name="integration", python=SUPPORTED_PYTHON_VERSIONS, tags=["tests", "docker", "integration"])
def integration_tests(session: Session) -> None:
    (here / ".coverage").unlink(missing_ok=True)
    session.run_install(
        "uv", "sync", "--all-extras", "--group=test", env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location}
    )
    args: list[str] = ["-m=integration", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args)


@nox.session(
    name="integration-postgres",
    python=SUPPORTED_PYTHON_VERSIONS,
    tags=["tests", "docker", "integration", "ci", "postgres"],
)
def integration_postgres_tests(session: Session) -> None:
    (here / ".coverage").unlink(missing_ok=True)
    session.run_install(
        "uv", "sync", "--all-extras", "--group=test", env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location}
    )
    args: list[str] = ["-m=asyncpg or psycopg_async or psycopg_sync", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args)


@nox.session(
    name="integration-mysql", python=SUPPORTED_PYTHON_VERSIONS, tags=["tests", "docker", "integration", "ci", "mysql"]
)
def integration_mysql_tests(session: Session) -> None:
    (here / ".coverage").unlink(missing_ok=True)
    session.run_install(
        "uv", "sync", "--all-extras", "--group=test", env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location}
    )
    args: list[str] = ["-m=asyncmy", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args)


@nox.session(
    name="integration-sqlite", python=SUPPORTED_PYTHON_VERSIONS, tags=["tests", "docker", "integration", "ci", "sqlite"]
)
def integration_sqlite_tests(session: Session) -> None:
    (here / ".coverage").unlink(missing_ok=True)
    session.run_install(
        "uv", "sync", "--all-extras", "--group=test", env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location}
    )
    args: list[str] = ["-m aiosqlite or sqlite", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args)
