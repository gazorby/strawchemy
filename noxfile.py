from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import nox

if TYPE_CHECKING:
    from nox import Session

PYTHON_VERSIONS = ["3.12"]
PYRIGHT_PYTHON_PYLANCE_VERSION: Literal["latest-release", "latest-prerelease"] = "latest-release"
PYRIGHT_PYTHON_FORCE_VERSION: str | None = None


nox.options.error_on_external_run = True
nox.options.default_venv_backend = "uv"


@nox.session(name="pyright", python=PYTHON_VERSIONS, tags=["lint"])
def pyright(session: Session) -> None:
    session.run_install(
        "uv",
        "sync",
        "--group=lint",
        "--all-extras",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    env = {"PYRIGHT_PYTHON_PYLANCE_VERSION": PYRIGHT_PYTHON_PYLANCE_VERSION}
    if PYRIGHT_PYTHON_FORCE_VERSION:
        env["PYRIGHT_PYTHON_FORCE_VERSION"] = PYRIGHT_PYTHON_FORCE_VERSION
    session.run("pyright", "--version", external=True, env=env)
    session.run("pyright", *session.posargs, external=True, env=env)


@nox.session(name="vulture", python=PYTHON_VERSIONS, tags=["lint"])
def vulture(session: Session) -> None:
    session.run_install(
        "uv",
        "sync",
        "--group=lint",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    session.run("vulture", "src/", "--min-confidence=100", "--sort-by-size", external=True)
