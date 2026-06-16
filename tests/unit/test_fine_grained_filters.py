from __future__ import annotations

from datetime import datetime
from datetime import datetime as _dt
from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from strawberry import UNSET
from strawberry.types import get_object_definition

from strawchemy import Strawchemy
from strawchemy.dto.strawberry import CustomFilter, CustomFilterFieldDefinition, Filter
from strawchemy.exceptions import StrawchemyFieldError
from strawchemy.schema.filters.fields import FilterFieldMarker
from strawchemy.schema.filters.inputs import OrderComparison, TextComparison

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

# Module-level convenience: `filter_field` is a Strawchemy method, but markers are
# mapper-agnostic, so a shared alias keeps the rest of the tests terse. Tests that
# specifically exercise the method call `Strawchemy("sqlite").filter_field(...)` directly.
_module_strawchemy = Strawchemy("sqlite")
filter_field = _module_strawchemy.filter_field


class _Base(DeclarativeBase): ...


class _Ticket(_Base):
    __tablename__ = "fgf_ticket"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    published_at: Mapped[datetime] = mapped_column()


def test_filter_field_bare_returns_marker() -> None:
    marker = Strawchemy("sqlite").filter_field()
    assert isinstance(marker, FilterFieldMarker)
    assert marker.ops is None
    assert marker.apply is None


def test_filter_field_with_ops_normalizes_to_tuple() -> None:
    marker = Strawchemy("sqlite").filter_field(ops=["eq", "in", "like"])
    assert marker.ops == ("eq", "in", "like")
    assert marker.apply is None


def test_filter_field_with_apply_captures_callable_and_join() -> None:
    def _apply(statement: Any, *_args: Any, **_kwargs: Any) -> Any:
        return statement

    marker = Strawchemy("sqlite").filter_field(apply=_apply, join="in")
    assert marker.apply is _apply
    assert marker.join == "in"
    assert marker.ops is None


def test_filter_field_rejects_ops_and_apply_together() -> None:
    with pytest.raises(StrawchemyFieldError, match="mutually exclusive"):
        Strawchemy("sqlite").filter_field(ops=["eq"], apply=lambda s, _v, **_k: s)


def test_filter_field_rejects_unknown_join() -> None:
    with pytest.raises(StrawchemyFieldError, match="join"):
        Strawchemy("sqlite").filter_field(apply=lambda s, _v, **_k: s, join="bogus")  # ty: ignore[invalid-argument-type]


def test_restricted_exposes_only_selected_ops() -> None:
    cls = TextComparison.restricted(str, ("eq", "in", "like"))
    exposed = {f.graphql_name or f.name for f in get_object_definition(cls, strict=True).fields}
    assert exposed == {"eq", "in", "like"}


def test_restricted_keeps_unselected_attrs_unset_at_runtime() -> None:
    cls = TextComparison.restricted(str, ("eq",))
    instance = cls()
    assert instance.gt is UNSET  # unselected op still present (UNSET) so query-time filters work
    assert instance.like is UNSET


def test_restricted_carries_base_filter() -> None:
    cls = TextComparison.restricted(str, ("eq",))
    assert cls.__strawchemy_comparison__.filter is TextComparison.__strawchemy_comparison__.filter


def test_restricted_invalid_op_raises() -> None:
    with pytest.raises(StrawchemyFieldError, match="frobnicate"):
        TextComparison.restricted(str, ("eq", "frobnicate"))


def test_restricted_is_deduped() -> None:
    a = TextComparison.restricted(str, ("eq", "like"))
    b = TextComparison.restricted(str, ("like", "eq"))  # order-independent
    assert a is b


def test_restricted_over_int_carries_int() -> None:
    cls = OrderComparison.restricted(int, ("eq", "gt"))
    eq_field = next(f for f in get_object_definition(cls, strict=True).fields if f.name == "eq")
    eq_type = eq_field.type
    # strawberry wraps `int | None` as a StrawberryOptional whose `of_type` is the scalar
    eq_type = getattr(eq_type, "of_type", eq_type)
    assert int in getattr(eq_type, "__args__", (eq_type,))


def test_custom_filter_is_filter_member() -> None:
    cf = CustomFilter(apply=lambda s, _v, **_k: s, value=5, join="exists", field_node=None)  # ty: ignore[invalid-argument-type]
    f = Filter(and_=[cf])
    assert f.and_ == [cf]


def test_custom_filter_field_definition_carries_marker_data() -> None:
    from datetime import datetime

    from strawchemy.dto.types import DTOConfig, Purpose

    def _apply(statement: Any, _value: Any, **_ctx: Any) -> Any:
        return statement

    field_def = CustomFilterFieldDefinition(
        dto_config=DTOConfig(Purpose.READ),
        model=object,  # ty: ignore[invalid-argument-type]
        model_field_name="published_after",
        type_hint=datetime,
        apply=_apply,
        join="exists",
    )
    assert field_def.apply is _apply
    assert field_def.join == "exists"


def test_parse_declared_fields_collects_restricted_and_custom() -> None:
    sc = Strawchemy("sqlite")

    def _apply(statement: Any, _value: Any, **_ctx: Any) -> Any:
        return statement

    class TicketFilter:
        name: str = sc.filter_field(ops=["eq", "in", "like"])
        published_after: _dt = sc.filter_field(apply=_apply)

    declared = sc.filter_factory.parse_declared_filter_fields(TicketFilter)
    assert set(declared) == {"name", "published_after"}

    name_marker, name_annotation = declared["name"]
    assert name_marker.ops == ("eq", "in", "like")
    assert name_annotation is str  # data type from the annotation

    custom_marker, custom_annotation = declared["published_after"]
    assert custom_marker.apply is _apply
    assert custom_annotation is _dt


def test_parse_declared_fields_requires_annotation() -> None:
    sc = Strawchemy("sqlite")

    class Bad:
        # restricted field with no annotation -> no data type to build a comparison
        name = sc.filter_field(ops=["eq"])

    with pytest.raises(StrawchemyFieldError, match="annotation"):
        sc.filter_factory.parse_declared_filter_fields(Bad)


def test_restricted_field_overrides_auto_comparison() -> None:
    strawchemy = Strawchemy("sqlite")

    @strawchemy.filter(_Ticket, include=["name"])
    class TicketFilter:
        # The annotation is the comparison type (documentary); the data type comes from the column.
        name: TextComparison = filter_field(ops=["eq", "like"])

    definition = get_object_definition(TicketFilter, strict=True)
    name_field = next(f for f in definition.fields if (f.graphql_name or f.name) == "name")
    comparison = name_field.type
    # strawberry wraps `Comparison | None` as a StrawberryOptional whose `of_type` is the comparison
    comparison_origin = getattr(comparison, "of_type", comparison)
    inner = get_object_definition(comparison_origin, strict=True)
    exposed = {f.graphql_name or f.name for f in inner.fields}
    assert exposed == {"eq", "like"}


def test_filter_field_forwards_strawberry_field_args() -> None:
    """filter_field()'s strawberry.field kwargs reach the generated GraphQL input field."""
    strawchemy = Strawchemy("sqlite")

    @strawchemy.filter(_Ticket, include=["name"])
    class TicketFilter:
        name: TextComparison = filter_field(
            ops=["eq"],
            name="renamedName",
            description="Filter by ticket name",
            deprecation_reason="use something else",
            metadata={"k": "v"},
        )

    definition = get_object_definition(TicketFilter, strict=True)
    field = next(f for f in definition.fields if (f.graphql_name or f.name) == "renamedName")
    assert field.description == "Filter by ticket name"
    assert field.deprecation_reason == "use something else"
    assert field.metadata == {"k": "v"}


def test_restricted_field_comparison_annotation_mismatch_raises() -> None:
    strawchemy = Strawchemy("sqlite")

    with pytest.raises(StrawchemyFieldError, match="OrderComparison"):

        @strawchemy.filter(_Ticket, include=["name"])
        class TicketFilter:
            # `name` is a str column -> TextComparison; OrderComparison is the wrong shape.
            name: OrderComparison = filter_field(ops=["eq"])


def test_custom_apply_field_injected_as_scalar() -> None:
    strawchemy = Strawchemy("sqlite")

    def _published_after(statement, value, **_ctx):  # noqa: ANN001, ANN003, ANN202
        return statement.where(_Ticket.published_at >= value)

    @strawchemy.filter(_Ticket, include=["name"])
    class TicketFilter:
        published_after: datetime = filter_field(apply=_published_after)

    definition = get_object_definition(TicketFilter, strict=True)
    # camelCase is applied at schema build time; the object definition keeps the python name
    field = next((f for f in definition.fields if (f.graphql_name or f.name) == "published_after"), None)
    assert field is not None


def test_filters_tree_wraps_custom_field() -> None:
    strawchemy = Strawchemy("sqlite")

    def _published_after(statement, value, **_ctx):  # noqa: ANN001, ANN003, ANN202
        return statement.where(_Ticket.published_at >= value)

    @strawchemy.filter(_Ticket, include=["name"])
    class TicketFilter:
        published_after: datetime = filter_field(apply=_published_after)

    instance = TicketFilter()
    instance.published_after = datetime(2024, 1, 1)  # ty: ignore[unresolved-attribute]  # noqa: DTZ001
    _node, query = instance.filters_tree()

    assert any(isinstance(item, CustomFilter) for item in query.and_)
    custom = next(item for item in query.and_ if isinstance(item, CustomFilter))
    assert custom.apply is _published_after
    assert custom.value == datetime(2024, 1, 1)  # noqa: DTZ001


def test_public_surface_end_to_end() -> None:
    sc = Strawchemy("sqlite")
    assert callable(sc.filter_field)

    def _published_after(statement, value, **_ctx):  # noqa: ANN001, ANN003, ANN202
        return statement.where(_Ticket.published_at >= value)

    @sc.filter(_Ticket, include=["name"])
    class TicketFilter:
        name: str = sc.filter_field(ops=["eq"])
        published_after: datetime = sc.filter_field(apply=_published_after)

    definition = get_object_definition(TicketFilter, strict=True)
    exposed = {f.graphql_name or f.name for f in definition.fields}
    assert "name" in exposed
    assert "published_after" in exposed


def test_restricted_field_on_unknown_column_raises() -> None:
    from strawchemy.exceptions import StrawchemyFieldError

    sc = Strawchemy("sqlite")
    with pytest.raises(StrawchemyFieldError, match="nonexistent"):

        @sc.filter(_Ticket, include=["name"])
        class TicketFilter:
            nonexistent: str = filter_field(ops=["eq"])


def test_invalid_operator_raises_at_definition() -> None:
    from strawchemy.exceptions import StrawchemyFieldError

    sc = Strawchemy("sqlite")
    with pytest.raises(StrawchemyFieldError, match="frobnicate"):

        @sc.filter(_Ticket, include=["name"])
        class TicketFilter:
            name: str = filter_field(ops=["frobnicate"])


@pytest.mark.snapshot
def test_fine_grained_schema(graphql_snapshot: SnapshotAssertion) -> None:
    sc = Strawchemy("sqlite")

    def _published_after(statement: Any, value: Any, **_ctx: Any) -> Any:
        return statement.where(_Ticket.published_at >= value)

    @sc.type(_Ticket, include=["name", "published_at"])
    class TicketType: ...

    @sc.filter(_Ticket, include=["name", "published_at"])
    class TicketFilter:
        name: TextComparison = filter_field(ops=["eq", "in", "like"])
        published_after: datetime = filter_field(apply=_published_after)

    @strawberry.type
    class Query:
        tickets: list[TicketType] = sc.field(filter_input=TicketFilter)

    schema = strawberry.Schema(query=Query)
    assert str(schema) == graphql_snapshot
