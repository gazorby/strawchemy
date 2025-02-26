from __future__ import annotations

from uuid import uuid4

import pytest
from strawchemy.dto.utils import read_all_config, write_all_config

from tests.models import Admin, Book, Tomato
from tests.typing import AnyFactory
from tests.utils import DTOInspect, factory_iterator


@pytest.mark.parametrize("factory", factory_iterator())
def test_to_mapped(factory: AnyFactory) -> None:
    dto = factory.factory(Tomato, read_all_config)
    uuid = uuid4()
    instance = dto(name="foo", id=uuid).to_mapped()  # pyright: ignore[reportCallIssue]
    assert isinstance(instance, Tomato)
    assert instance.id == uuid
    assert instance.name == "foo"


@pytest.mark.parametrize("factory", factory_iterator())
def test_default_read_write(factory: AnyFactory) -> None:
    write_dto = factory.factory(Admin, write_all_config)
    read_dto = factory.factory(Admin, read_all_config)
    assert DTOInspect(write_dto).has_init_arg("name")
    assert DTOInspect(read_dto).has_init_arg("name")


@pytest.mark.parametrize("factory", factory_iterator())
def test_write_only_field(factory: AnyFactory) -> None:
    write_dto = factory.factory(Admin, write_all_config)
    read_dto = factory.factory(Admin, read_all_config)
    assert DTOInspect(write_dto).has_init_arg("password")
    assert not DTOInspect(read_dto).has_init_arg("password")


@pytest.mark.parametrize("factory", factory_iterator())
def test_read_only_field(factory: AnyFactory) -> None:
    read_dto = factory.factory(Book, read_all_config)
    write_dto = factory.factory(Book, write_all_config)
    assert DTOInspect(read_dto).has_init_arg("isbn")
    assert not DTOInspect(write_dto).has_init_arg("isbn")


@pytest.mark.parametrize("factory", factory_iterator())
def test_private_field(factory: AnyFactory) -> None:
    read_dto = factory.factory(Admin, read_all_config)
    write_dto = factory.factory(Admin, write_all_config)
    assert not DTOInspect(read_dto).has_init_arg("private")
    assert not DTOInspect(write_dto).has_init_arg("private")
