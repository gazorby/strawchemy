from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
import strawberry
from strawberry.annotation import StrawberryAnnotation
from strawberry.types.arguments import StrawberryArgument

from strawchemy import Strawchemy
from tests.unit.models import Color
from tests.unit.utils import MockContext

if TYPE_CHECKING:
    from sqlalchemy import Select

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Color, include="all")
class ColorType: ...


@strawberry.type
class Query:
    color_by_pk: ColorType | None = strawchemy.field(id_field_name="pk")
    color_by_custom_argument: ColorType | None = strawchemy.field(
        id_field_name="pk", arguments=[StrawberryArgument("id", None, type_annotation=StrawberryAnnotation(UUID))]
    )


schema = strawberry.Schema(query=Query)


@pytest.mark.parametrize(("field", "argument"), [("colorByPk", "pk"), ("colorByCustomArgument", "id")])
def test_get_by_id_filters_on_primary_key(field: str, argument: str, captured_statements: list[Select[Any]]) -> None:
    """Test that a get-by-id field filters on the primary key whether its argument is generated or user-supplied."""
    color_id = uuid4()
    result = schema.execute_sync(
        f"query ($value: UUID!) {{ {field}({argument}: $value) {{ name }} }}",
        variable_values={"value": str(color_id)},
        context_value=MockContext("postgresql"),
    )

    assert not result.errors
    assert captured_statements[0].compile().params == {"id_1": color_id}
