from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

import nox

if TYPE_CHECKING:
    from nox import Session

DEFAULT_PYTHON_VERSION = "3.13"
SUPPORED_PYTHON_VERSIONS = ["3.9", "3.10", "3.11", "3.12", "3.13"]
PYRIGHT_PYTHON_PYLANCE_VERSION: Literal["latest-release", "latest-prerelease"] = "latest-release"
PYRIGHT_PYTHON_FORCE_VERSION: str | None = None
COMMON_PYTEST_OPTIONS = [
    "--cov-config=./pyproject.toml",
    "--cov=src",
    "--cov-append",
    "--cov-report=xml",
    "-n=2",
    "--showlocals",
]

here = Path(__file__).parent


nox.options.error_on_external_run = True
nox.options.default_venv_backend = "uv"


@nox.session(name="unit", python=SUPPORED_PYTHON_VERSIONS, tags=["tests"])
def unit_tests(session: Session) -> None:
    (here / ".coverage").unlink(missing_ok=True)
    session.run_install(
        "uv",
        "sync",
        "--all-extras",
        "--group=test",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    test_files: list[str] = session.posargs or []
    session.run("pytest", *COMMON_PYTEST_OPTIONS, "-vv", *test_files)


@nox.session(name="integration", python=SUPPORED_PYTHON_VERSIONS, tags=["tests", "docker"])
def integration_tests(session: Session) -> None:
    (here / ".coverage").unlink(missing_ok=True)
    session.run_install(
        "uv",
        "sync",
        "--all-extras",
        "--group=test",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    test_files: list[str] = session.posargs or [str(here / "tests" / "integration")]
    session.run("pytest", *COMMON_PYTEST_OPTIONS, "-vv", *test_files)
