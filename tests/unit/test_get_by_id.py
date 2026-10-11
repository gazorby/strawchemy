from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from strawberry.annotation import StrawberryAnnotation
from strawberry.types.arguments import StrawberryArgument

from strawchemy import Strawchemy
from strawchemy.dto.types import Purpose, PurposeConfig
from strawchemy.dto.utils import field
from tests.unit.models import Color
from tests.unit.utils import MockContext

if TYPE_CHECKING:
    from sqlalchemy import Select

strawchemy = Strawchemy("postgresql")


class _Base(DeclarativeBase): ...


class _AliasedKey(_Base):
    __tablename__ = "get_by_id_aliased_key"
    id: Mapped[UUID] = mapped_column(primary_key=True, info=field(configs={Purpose.READ: PurposeConfig(alias="pk")}))


@strawchemy.type(Color, include="all")
class ColorType: ...


@strawchemy.type(_AliasedKey, include="all")
class AliasedKeyType: ...


@strawberry.type
class Query:
    color_by_pk: ColorType | None = strawchemy.field(id_field_name="pk")
    color_by_custom_argument: ColorType | None = strawchemy.field(
        id_field_name="pk", arguments=[StrawberryArgument("id", None, type_annotation=StrawberryAnnotation(UUID))]
    )
    aliased_key: AliasedKeyType | None = strawchemy.field()
    aliased_key_by_pk: AliasedKeyType | None = strawchemy.field(id_field_name="pk")


schema = strawberry.Schema(query=Query)


@pytest.mark.parametrize(
    ("field", "argument", "selection"),
    [
        ("colorByPk", "pk", "name"),
        ("colorByCustomArgument", "id", "name"),
        ("aliasedKey", "id", "pk"),
        ("aliasedKeyByPk", "pk", "pk"),
    ],
)
def test_get_by_id_filters_on_primary_key(
    field: str, argument: str, selection: str, captured_statements: list[Select[Any]]
) -> None:
    """Test that a get-by-id field filters on the primary key, whatever its argument or the key's alias."""
    color_id = uuid4()
    result = schema.execute_sync(
        f"query ($value: UUID!) {{ {field}({argument}: $value) {{ {selection} }} }}",
        variable_values={"value": str(color_id)},
        context_value=MockContext("postgresql"),
    )

    assert not result.errors
    assert captured_statements[0].compile().params == {"id_1": color_id}
