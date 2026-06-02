from __future__ import annotations

import re
from typing import Optional
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from typing_extensions import Self

import strawchemy
from strawchemy import ALL, RELATIONSHIPS, SCALARS
from strawchemy.dto import DTOConfig, Purpose, PurposeConfig, config, field
from strawchemy.dto.base import DTOFieldDefinition
from strawchemy.dto.constants import DTO_INFO_KEY
from strawchemy.dto.strawberry import DTOKey, GraphQLFieldDefinition, StrawchemyDefinition
from strawchemy.dto.types import FieldGroup, include_field
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


def _fruit_field(name: str, *, is_relation: bool) -> DTOFieldDefinition:  # type: ignore[type-arg]
    return DTOFieldDefinition(
        dto_config=DTOConfig(Purpose.READ),
        model=Fruit,
        model_field_name=name,
        type_hint=int,
        is_relation=is_relation,
    )


class _PopulateFieldsBase(DeclarativeBase):
    pass


class _PopulateFieldsModel(_PopulateFieldsBase):
    __tablename__ = "populate_fields_model"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


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
            "color": color_dto(id=color_uuid, name="red", fruits=[]),  # ty: ignore[unknown-argument]
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
        assert DTOInspect(tomato_dto).field_type("popularity") == Optional[float]
    else:
        assert not DTOInspect(tomato_dto).has_init_field("sugarness")
        assert DTOInspect(tomato_dto).field_type("weight") is float
        assert DTOInspect(tomato_dto).field_type("popularity") is float


@pytest.mark.parametrize("model", [Tomato, TomatoDataclass])
@pytest.mark.parametrize("factory", factory_iterator())
def test_field_validator(factory: AnyFactory, model: type[Tomato | TomatoDataclass]) -> None:
    tomato_dto = factory.factory(model, write_all_config)

    with pytest.raises(ValueError, match=re.escape("We do not allow rotten tomato.")):
        tomato_dto(name="rotten", weight=1, sugarness=1, popularity=1)  # ty: ignore[unknown-argument]


@pytest.mark.parametrize("model", [Tomato, TomatoDataclass])
@pytest.mark.parametrize("factory", factory_iterator())
def test_field_alias(factory: AnyFactory, model: type[Tomato | TomatoDataclass]) -> None:
    tomato_dto = factory.factory(model, write_all_config)

    tomato = tomato_dto(name="good", weight=1, sugarness=1.25, popularity=1)  # ty: ignore[unknown-argument]

    assert tomato.sugarness == 1.25  # ty: ignore[unresolved-attribute]
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
    assert DTOInspect(user_dto).field_type("sponsor") == Optional[Self]  # ty: ignore[invalid-type-form]
    assert DTOInspect(user_dto).field_type("sponsored") == list[Self]  # ty: ignore[invalid-type-form]


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


# Tests for DTOConfig.from_include() and is_field_included()


def test_from_include_with_none() -> None:
    """Test that from_include(None) creates a config with empty include set."""
    config = DTOConfig.from_include(None)
    assert config.include == set()
    assert config.purpose == Purpose.READ


def test_from_include_with_all() -> None:
    """Test that from_include('all') creates a config with include='all'."""
    config = DTOConfig.from_include("all")
    assert config.include == "all"
    assert config.purpose == Purpose.READ


def test_from_include_with_list() -> None:
    """Test that from_include() accepts a list and converts it to the include parameter."""
    config = DTOConfig.from_include(["field1", "field2"])
    assert config.include == ["field1", "field2"]
    assert config.purpose == Purpose.READ


def test_from_include_with_set() -> None:
    """Test that from_include() accepts a set for the include parameter."""
    config = DTOConfig.from_include({"field1", "field2"})
    assert config.include == {"field1", "field2"}
    assert config.purpose == Purpose.READ


def test_from_include_with_custom_purpose() -> None:
    """Test that from_include() accepts a custom purpose."""
    config = DTOConfig.from_include(["field1"], purpose=Purpose.WRITE)
    assert config.include == ["field1"]
    assert config.purpose == Purpose.WRITE


def test_is_field_included_with_all() -> None:
    """Test that is_field_included() returns True for any field when include='all'."""
    config = DTOConfig.from_include("all")
    assert config.is_field_included("any_field") is True
    assert config.is_field_included("another_field") is True


def test_is_field_included_with_specific_list() -> None:
    """Test that is_field_included() returns True only for listed fields."""
    config = DTOConfig.from_include(["field1", "field2"])
    assert config.is_field_included("field1") is True
    assert config.is_field_included("field2") is True
    assert config.is_field_included("field3") is False


def test_is_field_included_with_empty_include() -> None:
    """Test that is_field_included() returns False for all fields when include is empty."""
    config = DTOConfig.from_include(None)
    assert config.is_field_included("field1") is False
    assert config.is_field_included("any_field") is False


def test_is_field_included_with_exclude() -> None:
    """Test that excluded fields are properly excluded even when include='all'."""
    config = DTOConfig(Purpose.READ, include="all", exclude={"field2", "field3"})
    assert config.is_field_included("field1") is True
    assert config.is_field_included("field2") is False
    assert config.is_field_included("field3") is False
    assert config.is_field_included("field4") is True


@pytest.mark.parametrize(
    "key_source",
    [_PopulateFieldsModel, DTOKey([_PopulateFieldsModel])],
    ids=["model-type", "dto-key"],
)
def test_strawchemy_definition_populate_fields(key_source: type[DeclarativeBase] | DTOKey) -> None:
    field_def = GraphQLFieldDefinition(
        config=DTOFieldConfig(),
        dto_config=DTOConfig(Purpose.READ),
        model=_PopulateFieldsModel,
        model_field_name="id",
        type_hint=int,
    )

    definition = StrawchemyDefinition()
    result = definition.populate_fields(key_source, [field_def])

    assert result is definition
    assert definition.field_map == {DTOKey([_PopulateFieldsModel]) + "id": field_def}


def test_field_group_constants_are_enum_members() -> None:
    """Test that the top-level SCALARS/RELATIONSHIPS constants are the enum members."""
    assert strawchemy.SCALARS is FieldGroup.SCALARS
    assert strawchemy.RELATIONSHIPS is FieldGroup.RELATIONSHIPS


def test_field_group_constants_hashable_in_sets() -> None:
    """Test that group constants are usable inside include/exclude frozensets."""
    members = frozenset([strawchemy.SCALARS, strawchemy.RELATIONSHIPS, "name"])
    assert strawchemy.SCALARS in members
    assert strawchemy.RELATIONSHIPS in members
    assert "name" in members


def test_scalars_include_allows_exclude() -> None:
    """Test that a group-bearing include coexists with exclude and is not clobbered to 'all'."""
    config = DTOConfig(Purpose.READ, include=[SCALARS], exclude=["secret"])
    assert config.include != "all"
    assert SCALARS in config.include
    assert "secret" in config.exclude


def test_plain_include_with_exclude_still_raises() -> None:
    """Test that a plain field-name include combined with exclude still raises."""
    with pytest.raises(ValueError, match="exclude"):
        DTOConfig(Purpose.READ, include=["a", "b"], exclude=["c"])


def test_bare_exclude_still_implies_all() -> None:
    """Test that a bare exclude (no include) still implies include='all'."""
    config = DTOConfig(Purpose.READ, exclude=["secret"])
    assert config.include == "all"


def test_relationships_exclude_implies_all_include() -> None:
    """Test that exclude=[RELATIONSHIPS] with no include promotes include to 'all'."""
    config = DTOConfig(Purpose.READ, exclude=[RELATIONSHIPS])
    assert config.include == "all"
    assert RELATIONSHIPS in config.exclude


def test_mixed_group_and_name_include_allows_exclude() -> None:
    """Test that a group selector mixed with a field name coexists with exclude."""
    config = DTOConfig(Purpose.READ, include=[SCALARS, "owner"], exclude=["secret"])
    assert config.include != "all"
    assert SCALARS in config.include
    assert "owner" in config.include
    assert "secret" in config.exclude


def test_global_group_include_allows_global_exclude() -> None:
    """Test that a group-bearing global_include coexists with global_exclude."""
    config = DTOConfig(Purpose.READ, global_include=[SCALARS], global_exclude=["secret"])
    assert config.global_include != "all"
    assert SCALARS in config.global_include
    assert "secret" in config.global_exclude


@pytest.mark.parametrize("factory", factory_iterator())
def test_include_scalars_excludes_relationships(factory: AnyFactory) -> None:
    """Test that include=[SCALARS] keeps scalar fields and drops relationships."""
    dto = factory.factory(Fruit, DTOConfig(Purpose.READ, include=[SCALARS]))
    fields = set(DTOInspect(dto).annotations())
    assert "color" not in fields
    assert {"id", "name", "sweetness", "color_id"} <= fields


@pytest.mark.parametrize("factory", factory_iterator())
def test_include_scalars_plus_named_relationship(factory: AnyFactory) -> None:
    """Test that include=[SCALARS, 'color'] keeps scalars plus the named relationship."""
    dto = factory.factory(Fruit, DTOConfig(Purpose.READ, include=[SCALARS, "color"]))
    fields = set(DTOInspect(dto).annotations())
    assert "color" in fields
    assert {"id", "name", "sweetness", "color_id"} <= fields


@pytest.mark.parametrize("factory", factory_iterator())
def test_include_relationships_only(factory: AnyFactory) -> None:
    """Test that include=[RELATIONSHIPS] keeps only relationships and drops scalars."""
    dto = factory.factory(Fruit, DTOConfig(Purpose.READ, include=[RELATIONSHIPS]))
    fields = set(DTOInspect(dto).annotations())
    assert "color" in fields
    assert "name" not in fields
    assert "sweetness" not in fields
    assert "color_id" not in fields


@pytest.mark.parametrize("factory", factory_iterator())
def test_include_both_groups_equals_all(factory: AnyFactory) -> None:
    """Test that include=[SCALARS, RELATIONSHIPS] is equivalent to include='all'."""
    grouped = factory.factory(Fruit, DTOConfig(Purpose.READ, include=[SCALARS, RELATIONSHIPS]))
    all_dto = factory.factory(Fruit, read_all_config)
    assert set(DTOInspect(grouped).annotations()) == set(DTOInspect(all_dto).annotations())


@pytest.mark.parametrize("factory", factory_iterator())
def test_exclude_relationships_keeps_scalars(factory: AnyFactory) -> None:
    """Test that exclude=[RELATIONSHIPS] keeps all scalar fields and walks no relationships."""
    dto = factory.factory(Fruit, DTOConfig(Purpose.READ, exclude=[RELATIONSHIPS]))
    fields = set(DTOInspect(dto).annotations())
    assert "color" not in fields
    assert {"id", "name", "sweetness", "color_id"} <= fields


@pytest.mark.parametrize("factory", factory_iterator())
def test_exclude_relationships_plus_named_scalar(factory: AnyFactory) -> None:
    """Test that exclude=[RELATIONSHIPS, 'sweetness'] drops relationships and the named scalar."""
    dto = factory.factory(Fruit, DTOConfig(Purpose.READ, exclude=[RELATIONSHIPS, "sweetness"]))
    fields = set(DTOInspect(dto).annotations())
    assert "color" not in fields
    assert "sweetness" not in fields
    assert {"id", "name", "color_id"} <= fields


def test_is_field_included_relationships_group_matches_relations() -> None:
    """Test that include=[RELATIONSHIPS] includes relation fields and excludes scalars."""
    config = DTOConfig(Purpose.READ, include=frozenset([RELATIONSHIPS]))
    assert config.is_field_included(_fruit_field("owner", is_relation=True)) is True
    assert config.is_field_included(_fruit_field("name", is_relation=False)) is False


def test_is_field_included_scalars_group_matches_scalars() -> None:
    """Test that include=[SCALARS] includes scalar fields and excludes relations."""
    config = DTOConfig(Purpose.READ, include=frozenset([SCALARS]))
    assert config.is_field_included(_fruit_field("name", is_relation=False)) is True
    assert config.is_field_included(_fruit_field("owner", is_relation=True)) is False


def test_is_field_included_group_in_exclude() -> None:
    """Test that a group selector in exclude drops matching fields."""
    config = DTOConfig(Purpose.READ, include="all", exclude=frozenset([RELATIONSHIPS]))
    assert config.is_field_included(_fruit_field("owner", is_relation=True)) is False
    assert config.is_field_included(_fruit_field("name", is_relation=False)) is True


def test_is_field_included_no_group_unchanged() -> None:
    """Test that behavior is unchanged when no group constants are present."""
    config = DTOConfig(Purpose.READ, include=frozenset(["a", "b"]))
    assert config.is_field_included("a") is True
    assert config.is_field_included("c") is False
    assert config.is_field_included(_fruit_field("a", is_relation=True)) is True


def test_string_literals_equal_field_group_members() -> None:
    """Test that plain string literals equal their FieldGroup members."""
    assert FieldGroup.ALL == "all"
    assert FieldGroup.SCALARS == "scalars"
    assert FieldGroup.RELATIONSHIPS == "relationships"


@pytest.mark.parametrize("factory", factory_iterator())
def test_include_string_scalars_literal(factory: AnyFactory) -> None:
    """Test that the literal include=['scalars'] behaves like include=[SCALARS]."""
    dto = factory.factory(Fruit, DTOConfig(Purpose.READ, include=["scalars"]))
    fields = set(DTOInspect(dto).annotations())
    assert "color" not in fields
    assert {"id", "name", "sweetness", "color_id"} <= fields


@pytest.mark.parametrize("factory", factory_iterator())
def test_include_all_literal_set_equals_all(factory: AnyFactory) -> None:
    """Test that include={'all'} is equivalent to include='all'."""
    grouped = factory.factory(Fruit, DTOConfig(Purpose.READ, include={"all"}))
    all_dto = factory.factory(Fruit, read_all_config)
    assert set(DTOInspect(grouped).annotations()) == set(DTOInspect(all_dto).annotations())


@pytest.mark.parametrize("factory", factory_iterator())
def test_include_all_constant_in_collection(factory: AnyFactory) -> None:
    """Test that include=[ALL] is equivalent to include='all'."""
    grouped = factory.factory(Fruit, DTOConfig(Purpose.READ, include=[ALL]))
    all_dto = factory.factory(Fruit, read_all_config)
    assert set(DTOInspect(grouped).annotations()) == set(DTOInspect(all_dto).annotations())


def test_include_field_all_selects_everything() -> None:
    """Test that include_field returns True for the 'all' selector."""
    assert include_field("anything", False, "all") is True
    assert include_field("anything", True, "all") is True
