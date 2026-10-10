from __future__ import annotations

from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional, Union
from unittest.mock import Mock

import pytest
from sqlalchemy import JSON, Column, Dialect, Integer, MetaData, Table, TypeDecorator
from sqlalchemy.dialects import postgresql

from strawchemy.exceptions import SessionNotFoundError
from strawchemy.utils.annotation import get_type_hints_partial, inner_types
from strawchemy.utils.postgres import as_jsonb, comparable
from strawchemy.utils.strawberry import default_session_getter

if TYPE_CHECKING:
    from sqlalchemy.types import TypeEngine

    from strawchemy.typing import SupportedDialect


@pytest.mark.parametrize(
    "info",
    [
        Mock(context=Mock(session="session")),
        Mock(context={"session": "session"}),
        Mock(context=Mock(spec=["request"], request=Mock(session="session"))),
        Mock(context={"request": Mock(session="session")}),
    ],
)
def test_session_getter(info: Mock) -> None:
    assert default_session_getter(info) == "session"


@pytest.mark.parametrize("info", [Mock(context=Mock(spec=[])), Mock(context={})])
def test_session_not_found_error(info: Mock) -> None:
    with pytest.raises(SessionNotFoundError):
        default_session_getter(info)


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (int, (int,)),
        (list[int], (int,)),
        (Optional[str], (str, type(None))),
        (dict[str, int], (str, int)),
        (list[Optional[int]], (int, type(None))),
        (Union[int, str, None], (int, str, type(None))),
    ],
)
def test_inner_types(annotation: object, expected: tuple[object, ...]) -> None:
    assert inner_types(annotation) == expected


def test_get_type_hints_partial_keeps_unresolvable_annotations() -> None:
    """Test that an unresolvable annotation stays raw while the inherited and resolvable ones are evaluated."""

    class Parent:
        parent_id: int

    class Child(Parent):
        name: str | None
        missing: list[NotDefinedYet]  # noqa: F821  # ty: ignore[unresolved-reference]

    assert get_type_hints_partial(Child) == {
        "parent_id": int,
        "name": Optional[str],
        "missing": "list[NotDefinedYet]",
    }


def test_get_type_hints_partial_resolves_class_body_names() -> None:
    """Test that a name defined in the class body resolves even when a sibling annotation is unresolvable."""

    class Fruit:
        class Kind(Enum):
            APPLE = "apple"

        kind: Kind
        missing: NotDefinedYet  # noqa: F821  # ty: ignore[unresolved-reference]

    assert get_type_hints_partial(Fruit) == {"kind": Fruit.Kind, "missing": "NotDefinedYet"}


def test_get_type_hints_partial_module_names_shadow_class_attributes() -> None:
    """Test that a module name wins over a same-named class attribute when a sibling annotation is unresolvable."""

    class Event:
        date: date = date(2020, 1, 1)  # ty: ignore[invalid-type-form]  # deliberate shadowing
        missing: NotDefinedYet  # noqa: F821  # ty: ignore[unresolved-reference]

    assert get_type_hints_partial(Event) == {"date": date, "missing": "NotDefinedYet"}


class _JSONBDecorator(TypeDecorator[Any]):
    impl = postgresql.JSONB
    cache_ok = True


class _JSONBVariantDecorator(TypeDecorator[Any]):
    impl = JSON().with_variant(postgresql.JSONB, "postgresql")
    cache_ok = True


class _JSONBLoadedDecorator(TypeDecorator[Any]):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        return dialect.type_descriptor(postgresql.JSONB())


class _JSONDecorator(TypeDecorator[Any]):
    impl = postgresql.JSON
    cache_ok = True


@pytest.mark.parametrize(
    ("type_", "expected"),
    [
        pytest.param(postgresql.JSONB(), "t.c", id="jsonb"),
        pytest.param(JSON().with_variant(postgresql.JSONB, "postgresql"), "t.c", id="jsonb-variant"),
        pytest.param(_JSONBDecorator(), "t.c", id="jsonb-decorator"),
        pytest.param(_JSONBVariantDecorator(), "t.c", id="jsonb-variant-decorator"),
        pytest.param(_JSONBLoadedDecorator(), "t.c", id="jsonb-load-dialect-impl"),
        pytest.param(postgresql.JSON(), "CAST(t.c AS JSONB)", id="json"),
        pytest.param(JSON(), "CAST(t.c AS JSONB)", id="generic-json"),
        pytest.param(_JSONDecorator(), "CAST(t.c AS JSONB)", id="json-decorator"),
    ],
)
def test_as_jsonb(type_: TypeEngine[Any], expected: str) -> None:
    column = Table("t", MetaData(), Column("c", type_)).c.c
    assert str(as_jsonb(column).compile(dialect=postgresql.psycopg2.dialect())) == expected


@pytest.mark.parametrize(
    ("type_", "expected"),
    [
        pytest.param(Integer(), "t.c", id="integer"),
        pytest.param(postgresql.JSONB(), "t.c", id="jsonb"),
        pytest.param(_JSONBDecorator(), "t.c", id="jsonb-decorator"),
        pytest.param(postgresql.JSON(), "CAST(t.c AS JSONB)", id="json"),
        pytest.param(JSON(), "CAST(t.c AS JSONB)", id="generic-json"),
        pytest.param(_JSONDecorator(), "CAST(t.c AS JSONB)", id="json-decorator"),
    ],
)
def test_comparable(type_: TypeEngine[Any], expected: str) -> None:
    column = Table("t", MetaData(), Column("c", type_)).c.c
    assert str(comparable(column, "postgresql").compile(dialect=postgresql.psycopg2.dialect())) == expected


@pytest.mark.parametrize("dialect", ["mysql", "sqlite"])
def test_comparable_other_dialects(dialect: SupportedDialect) -> None:
    column = Table("t", MetaData(), Column("c", JSON())).c.c
    assert comparable(column, dialect) is column
