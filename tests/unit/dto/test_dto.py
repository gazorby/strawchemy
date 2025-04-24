from __future__ import annotations

from typing import Optional, Self
from uuid import UUID, uuid4

import pytest
from strawchemy.dto import DTOConfig, Purpose, PurposeConfig, config, field
from strawchemy.dto.constants import DTO_INFO_KEY
from strawchemy.dto.utils import DTOFieldConfig, read_all_config, write_all_config

from tests.typing import AnyFactory, MappedPydanticFactory
from tests.unit.dc_models import (
    AdminDataclass,
    ColorDataclass,
    FruitDataclass,
    SponsoredUserDataclass,
    TomatoDataclass,
    UserWithGreetingDataclass,
)
from tests.unit.models import Admin, Book, Color, Fruit, SponsoredUser, Tag, Tomato, UserWithGreeting
from tests.utils import DTOInspect, factory_iterator


def test_config_function_produces_same_default() -> None:
    assert config(Purpose.READ) == DTOConfig(Purpose.READ)


def test_default_field_config() -> None:
    assert field()[DTO_INFO_KEY] == DTOFieldConfig(
        purposes={Purpose.READ, Purpose.WRITE}, configs={}, default_config=PurposeConfig()
    )


@pytest.mark.parametrize("model", [Tomato, TomatoDataclass])
@pytest.mark.parametrize("factory", factory_iterator())
def test_base_annotations_include(factory: AnyFactory, model: type[Tomato | TomatoDataclass]) -> None:
    class Base:
        name: str

    config = DTOConfig(Purpose.READ).with_base_annotations(Base)
    dto = factory.factory(model, config)

    assert DTOInspect(dto).annotations() == {"name": str}


@pytest.mark.parametrize("model", [Tomato, TomatoDataclass])
@pytest.mark.parametrize("factory", factory_iterator())
def test_base_annotations_include_override(factory: AnyFactory, model: type[Tomato | TomatoDataclass]) -> None:
    class Base:
        name: int

    config = DTOConfig(Purpose.READ, include={"name"}).with_base_annotations(Base)
    dto = factory.factory(model, config)

    assert DTOInspect(dto).annotations() == {"name": int}


@pytest.mark.parametrize("model", [Tomato, TomatoDataclass])
@pytest.mark.parametrize("factory", factory_iterator())
def test_base_annotations_exclude_override(factory: AnyFactory, model: type[Tomato | TomatoDataclass]) -> None:
    class Base:
        name: str

    config = DTOConfig(Purpose.READ, exclude={"name"}).with_base_annotations(Base)
    dto = factory.factory(model, config)

    assert DTOInspect(dto).annotations() == {
        "name": str,
        "id": UUID,
        "popularity": float,
        "sweetness": float,
        "weight": float,
    }


@pytest.mark.parametrize("models", [(Fruit, Color), (FruitDataclass, ColorDataclass)])
@pytest.mark.parametrize("factory", factory_iterator())
def test_to_mapped(
    factory: AnyFactory, models: tuple[type[Fruit | FruitDataclass], type[Color | ColorDataclass]]
) -> None:
    fruit_model, color_model = models
    fruit_dto = factory.factory(fruit_model, read_all_config)
    color_dto = factory.factory(color_model, read_all_config)
    fruit_uuid, color_uuid = uuid4(), uuid4()
    dto_instance = fruit_dto(
        **{  # noqa: PIE804
            "name": "foo",
            "id": fruit_uuid,
            "color": color_dto(id=color_uuid, name="red", fruits=[]),  # pyright: ignore[reportCallIssue]
            "color_id": color_uuid,
            "sweetness": 1,
        }
    )
    instance = dto_instance.to_mapped()
    # Test fruit
    assert isinstance(instance, fruit_model)
    assert instance.id == fruit_uuid
    assert instance.name == "foo"
    # Test color
    assert isinstance(instance.color, color_model)
    assert instance.color.id == color_uuid
    assert instance.color.name == "red"


@pytest.mark.parametrize("model", [Color, ColorDataclass])
@pytest.mark.parametrize("factory", factory_iterator())
def test_to_mapped_override(factory: AnyFactory, model: type[Color | ColorDataclass]) -> None:
    fruit_dto = factory.factory(model, read_all_config)
    uuid = uuid4()
    dto_instance = fruit_dto(**{"id": uuid, "name": "Green", "fruits": []})  # noqa: PIE804
    instance = dto_instance.to_mapped(override={"name": "Red"})
    assert instance.name == "Red"


@pytest.mark.parametrize("model", [Color, ColorDataclass])
@pytest.mark.parametrize("factory", factory_iterator())
def test_to_mapped_override_excluded(factory: AnyFactory, model: type[Color | ColorDataclass]) -> None:
    fruit_dto = factory.factory(model, DTOConfig(Purpose.READ, exclude={"name"}))
    uuid = uuid4()
    dto_instance = fruit_dto(**{"id": uuid, "fruits": []})  # noqa: PIE804
    instance = dto_instance.to_mapped(override={"name": "Red"})
    assert instance.name == "Red"


@pytest.mark.parametrize("model", [Admin, AdminDataclass])
@pytest.mark.parametrize("factory", factory_iterator())
def test_default_read_write(factory: AnyFactory, model: type[Admin | AdminDataclass]) -> None:
    write_dto = factory.factory(model, write_all_config)
    read_dto = factory.factory(model, read_all_config)
    assert DTOInspect(write_dto).has_init_field("name")
    assert DTOInspect(read_dto).has_init_field("name")


@pytest.mark.parametrize("model", [Admin, AdminDataclass])
@pytest.mark.parametrize("factory", factory_iterator())
def test_write_only_field(factory: AnyFactory, model: type[Admin | AdminDataclass]) -> None:
    write_dto = factory.factory(model, write_all_config)
    read_dto = factory.factory(model, read_all_config)
    assert DTOInspect(write_dto).has_init_field("password")
    assert not DTOInspect(read_dto).has_init_field("password")


@pytest.mark.parametrize("factory", factory_iterator())
def test_read_only_field(factory: AnyFactory) -> None:
    read_dto = factory.factory(Book, read_all_config)
    write_dto = factory.factory(Book, write_all_config)
    assert DTOInspect(read_dto).has_init_field("isbn")
    assert not DTOInspect(write_dto).has_init_field("isbn")


@pytest.mark.parametrize("model", [Admin, AdminDataclass])
@pytest.mark.parametrize("factory", factory_iterator())
def test_private_field(factory: AnyFactory, model: type[Admin | AdminDataclass]) -> None:
    read_dto = factory.factory(model, read_all_config)
    write_dto = factory.factory(model, write_all_config)
    assert not DTOInspect(read_dto).has_init_field("private")
    assert not DTOInspect(write_dto).has_init_field("private")


@pytest.mark.parametrize("model", [Tomato, TomatoDataclass])
@pytest.mark.parametrize("config", [write_all_config, read_all_config])
@pytest.mark.parametrize("factory", factory_iterator())
def test_model_field_config(factory: AnyFactory, config: DTOConfig, model: type[Tomato | TomatoDataclass]) -> None:
    tomato_dto = factory.factory(model, config)

    if config.purpose is Purpose.WRITE:
        assert DTOInspect(tomato_dto).has_init_field("sugarness")
        assert DTOInspect(tomato_dto).field_type("weight") is int
        assert DTOInspect(tomato_dto).field_type("popularity") == Optional[float]  # noqa: UP007
    else:
        assert not DTOInspect(tomato_dto).has_init_field("sugarness")
        assert DTOInspect(tomato_dto).field_type("weight") is float
        assert DTOInspect(tomato_dto).field_type("popularity") is float


@pytest.mark.parametrize("model", [Tomato, TomatoDataclass])
@pytest.mark.parametrize("factory", factory_iterator())
def test_field_validator(factory: AnyFactory, model: type[Tomato | TomatoDataclass]) -> None:
    tomato_dto = factory.factory(model, write_all_config)

    with pytest.raises(ValueError, match="We do not allow rotten tomato."):
        tomato_dto(name="rotten", weight=1, sugarness=1, popularity=1)  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize("model", [Tomato, TomatoDataclass])
@pytest.mark.parametrize("factory", factory_iterator())
def test_field_alias(factory: AnyFactory, model: type[Tomato | TomatoDataclass]) -> None:
    tomato_dto = factory.factory(model, write_all_config)

    tomato = tomato_dto(name="good", weight=1, sugarness=1.25, popularity=1)  # pyright: ignore[reportCallIssue]

    assert tomato.sugarness == 1.25  # pyright: ignore[reportAttributeAccessIssue]
    assert tomato.to_mapped().sweetness == 1.25


@pytest.mark.parametrize("model", [UserWithGreeting, UserWithGreetingDataclass])
@pytest.mark.parametrize("factory", factory_iterator())
def test_hybrid_property_excluded(
    factory: AnyFactory, model: type[UserWithGreeting | UserWithGreetingDataclass]
) -> None:
    user_dto = factory.factory(model, DTOConfig(Purpose.READ, include={"name", "greeting_hybrid_property"}))
    assert DTOInspect(user_dto).has_init_field("name")
    assert not DTOInspect(user_dto).has_init_field("greeting_hybrid_property")


@pytest.mark.parametrize("model", [UserWithGreeting, UserWithGreetingDataclass])
@pytest.mark.parametrize("factory", factory_iterator())
def test_column_property(factory: AnyFactory, model: type[UserWithGreeting | UserWithGreetingDataclass]) -> None:
    user_dto = factory.factory(model, DTOConfig(Purpose.READ, include={"greeting_column_property"}))
    assert DTOInspect(user_dto).has_init_field("greeting_column_property")


@pytest.mark.parametrize("model", [SponsoredUser, SponsoredUserDataclass])
@pytest.mark.parametrize("factory", factory_iterator())
def test_self_reference(factory: AnyFactory, model: type[SponsoredUser | SponsoredUserDataclass]) -> None:
    user_dto = factory.factory(model, read_all_config)
    assert DTOInspect(user_dto).field_type("sponsor") == Optional[Self]  # pyright: ignore[reportGeneralTypeIssues]  # noqa: UP007
    assert DTOInspect(user_dto).field_type("sponsored") == list[Self]  # pyright: ignore[reportGeneralTypeIssues]


@pytest.mark.parametrize("name", ["SomeTag", None])
def test_forward_refs_resolved(name: str, sqlalchemy_pydantic_factory: MappedPydanticFactory) -> None:
    tag_dto = sqlalchemy_pydantic_factory.factory(Tag, read_all_config, name=name)
    tag_dto.model_validate(
        {
            "id": uuid4(),
            "name": "tag 1",
            "groups": [
                {
                    "id": uuid4(),
                    "tag_id": uuid4(),
                    "tag": {
                        "id": uuid4(),
                        "name": "group tag",
                        "groups": [
                            {
                                "id": uuid4(),
                                "name": "another group",
                                "tag_id": uuid4(),
                                "color_id": uuid4(),
                                "color": {"id": uuid4(), "name": "red", "fruits": []},
                                "tag": {"id": uuid4(), "name": "group tag", "groups": []},
                                "users": [],
                            }
                        ],
                    },
                    "name": "group 1",
                    "color_id": uuid4(),
                    "color": {
                        "id": uuid4(),
                        "name": "red",
                        "fruits": [
                            {
                                "id": uuid4(),
                                "name": "Banana",
                                "color_id": uuid4(),
                                "sweetness": 2.0,
                                "color": {"id": uuid4(), "name": "Yellow", "fruits": []},
                            }
                        ],
                    },
                    "users": [],
                }
            ],
        }
    )
