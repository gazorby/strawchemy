from __future__ import annotations

from uuid import UUID

from strawchemy.dto.types import DTOConfig, Purpose
from strawchemy.dto.utils import config

from tests.models import Tomato
from tests.typing import MappedDataclassFactory


def test_base_annotations_include(sqlalchemy_dataclass_factory: MappedDataclassFactory) -> None:
    class Base:
        name: str

    config = DTOConfig(Purpose.READ).with_base_annotations(Base)
    dto = sqlalchemy_dataclass_factory.factory(Tomato, config)

    assert dto.__annotations__ == {"name": str}


def test_base_annotations_include_override(sqlalchemy_dataclass_factory: MappedDataclassFactory) -> None:
    class Base:
        name: int

    config = DTOConfig(Purpose.READ, include={"name"}).with_base_annotations(Base)
    dto = sqlalchemy_dataclass_factory.factory(Tomato, config)

    assert dto.__annotations__ == {"name": int}


def test_base_annotations_exclude_override(sqlalchemy_dataclass_factory: MappedDataclassFactory) -> None:
    class Base:
        name: str

    config = DTOConfig(Purpose.READ, exclude={"name"}).with_base_annotations(Base)
    dto = sqlalchemy_dataclass_factory.factory(Tomato, config)

    assert dto.__annotations__ == {"name": str, "id": UUID}


def test_default_config() -> None:
    assert config(Purpose.READ) == DTOConfig(Purpose.READ)
