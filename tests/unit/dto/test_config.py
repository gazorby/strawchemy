from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from strawchemy.dto.constants import DTO_INFO_KEY
from strawchemy.dto.types import DTOConfig, DTOFieldConfig, Purpose, PurposeConfig
from strawchemy.dto.utils import config, field

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
    assert asdict(DTOConfig(Purpose.READ)) == {
        "purpose": Purpose.READ,
        "include": set(),
        "exclude": set(),
        "partial": None,
        "type_overrides": {},
        "annotation_overrides": {},
        "aliases": {},
        "alias_generator": None,
    }


def test_config_function_produces_same_default() -> None:
    assert config(Purpose.READ) == DTOConfig(Purpose.READ)


def test_default_field_config() -> None:
    assert field()[DTO_INFO_KEY] == DTOFieldConfig(
        purposes={Purpose.READ, Purpose.WRITE}, configs={}, default_config=PurposeConfig()
    )
