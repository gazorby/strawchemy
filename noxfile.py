from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import nox
from nox_uv import session

if TYPE_CHECKING:
    from nox import Session

# SQLAlchemy 2.1 requires Python 3.11, so uv.lock resolves 2.0 on Python 3.10 only.
SQLALCHEMY_PYTHON_VERSIONS = {"2.0": ["3.10"], "2.1": ["3.11", "3.12", "3.13", "3.14"]}
SQLALCHEMY_MATRIX = [
    nox.param(python, sqlalchemy, id=f"{python}-sqlalchemy{sqlalchemy}")
    for sqlalchemy, pythons in SQLALCHEMY_PYTHON_VERSIONS.items()
    for python in pythons
]
COMMON_PYTEST_OPTIONS = ["--showlocals", "-vv", "-n=auto"]

here = Path(__file__).parent

nox.options.default_venv_backend = "uv"
# Discovery would otherwise prefer whatever interpreter the host happens to expose, and a distro python
# carries the distro's libsqlite3 with it.
nox.options.download_python = "always"
nox.options.reuse_venv = "yes"
nox.options.error_on_external_run = True
nox.options.error_on_missing_interpreters = True


def _check_sqlalchemy(session: Session, version: str) -> None:
    session.run(
        "python", "-c", f"import sqlalchemy, sys; sys.exit(not sqlalchemy.__version__.startswith('{version}.'))"
    )


def extras_env(*extras: str) -> dict[str, str]:
    return {"STRAWCHEMY_TEST_EXTRAS": ",".join(extras)}


@session(
    name="unit",
    tags=["tests", "unit", "ci"],
    uv_groups=["test"],
    uv_all_extras=True,
    uv_sync_locked=False,
)
@nox.parametrize("python,sqlalchemy", SQLALCHEMY_MATRIX)
def unit_tests(session: Session, sqlalchemy: str) -> None:
    _check_sqlalchemy(session, sqlalchemy)
    (here / ".coverage").unlink(missing_ok=True)
    args: list[str] = ["-m=not integration", "tests/unit", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args, env=extras_env("asyncio", "geo", "pydantic"))


@session(
    name="unit-no-extras",
    tags=["tests", "unit", "ci"],
    uv_groups=["test"],
    uv_sync_locked=False,
)
@nox.parametrize("python,sqlalchemy", SQLALCHEMY_MATRIX)
def unit_tests_no_extras(session: Session, sqlalchemy: str) -> None:
    _check_sqlalchemy(session, sqlalchemy)
    (here / ".coverage").unlink(missing_ok=True)
    args: list[str] = ["-m=not integration and not extras", "tests/unit", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args)


@session(
    name="integration",
    tags=["tests", "docker", "integration"],
    uv_groups=["test", "postgres", "mysql", "aiosqlite"],
    uv_extras=["asyncio", "geo"],
    uv_sync_locked=False,
)
@nox.parametrize("python,sqlalchemy", SQLALCHEMY_MATRIX)
def integration_tests(session: Session, sqlalchemy: str) -> None:
    _check_sqlalchemy(session, sqlalchemy)
    (here / ".coverage").unlink(missing_ok=True)
    args: list[str] = ["-m=integration", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args, env=extras_env("asyncio", "geo"))


@session(
    name="integration-postgres",
    tags=["tests", "docker", "integration", "ci", "postgres"],
    uv_groups=["test", "postgres"],
    uv_extras=["asyncio", "geo"],
    uv_sync_locked=False,
)
@nox.parametrize("python,sqlalchemy", SQLALCHEMY_MATRIX)
def integration_postgres_tests(session: Session, sqlalchemy: str) -> None:
    _check_sqlalchemy(session, sqlalchemy)
    (here / ".coverage").unlink(missing_ok=True)
    args: list[str] = ["-m=asyncpg or psycopg_async or psycopg_sync", "--snapshot-warn-unused", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args, env=extras_env("asyncio", "geo"))


@session(
    name="integration-mysql",
    tags=["tests", "docker", "integration", "ci", "mysql"],
    uv_groups=["test", "mysql"],
    uv_extras=["asyncio", "geo"],
    uv_sync_locked=False,
)
@nox.parametrize("python,sqlalchemy", SQLALCHEMY_MATRIX)
def integration_mysql_tests(session: Session, sqlalchemy: str) -> None:
    _check_sqlalchemy(session, sqlalchemy)
    (here / ".coverage").unlink(missing_ok=True)
    args: list[str] = ["-m=asyncmy", "--snapshot-warn-unused", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args, env=extras_env("asyncio", "geo"))


@session(
    name="integration-sqlite",
    tags=["tests", "docker", "integration", "ci", "sqlite"],
    uv_groups=["test", "aiosqlite"],
    uv_extras=["asyncio"],
    uv_sync_locked=False,
)
@nox.parametrize("python,sqlalchemy", SQLALCHEMY_MATRIX)
def integration_sqlite_tests(session: Session, sqlalchemy: str) -> None:
    _check_sqlalchemy(session, sqlalchemy)
    (here / ".coverage").unlink(missing_ok=True)
    args: list[str] = ["-m aiosqlite or sqlite", "--snapshot-warn-unused", *session.posargs]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, *args, env=extras_env("asyncio"))
