from __future__ import annotations

import pytest
from strawchemy import Strawchemy


@pytest.fixture(name="strawchemy_postgresql")
def fx_strawchemy_postgresql() -> Strawchemy:
    return Strawchemy("postgresql")


@pytest.fixture(name="strawchemy_sqlite")
def fx_strawchemy_sqlite() -> Strawchemy:
    return Strawchemy("sqlite")


@pytest.fixture(name="strawchemy_mysql")
def fx_strawchemy_mysql() -> Strawchemy:
    return Strawchemy("mysql")
