from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import strawberry
from sqlalchemy import Insert, insert

from tests.integration.fixtures import Operations, SchemaTypes
from tests.integration.models import Group, User
from tests.integration.typing import RawRecordData
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

_GROUPS: RawRecordData = [{"id": 1, "name": "Group 1"}]
_USERS: RawRecordData = [
    {"id": 1, "name": "Alice", "group_id": 1, "bio": None},
    {"id": 2, "name": "Bob", "group_id": None, "bio": None},
    {"id": 3, "name": "Charlie", "group_id": None, "bio": None},
    {"id": 4, "name": "Tango", "group_id": None, "bio": "Tango's bio"},
]
_ALL_USERS = sorted(user["name"] for user in _USERS)


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(User, include=["name"])
    class UserType: ...

    @strawchemy.filter(User, include=["name", "bio"])
    class UserFilter: ...

    @strawberry.type
    class Query:
        users: list[UserType] = strawchemy.field(filter_input=UserFilter)

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def user_rows() -> RawRecordData:
    return _USERS


@pytest.fixture
def seed_insert_statements(user_rows: RawRecordData) -> list[Insert]:
    return [insert(Group).values(_GROUPS), insert(User).values(user_rows)]


@pytest.mark.parametrize(
    ("dto_filter", "names"),
    [
        pytest.param('{ name: { regexp: "o", nregexp: "^B" } }', ["Tango"], id="regexp-and-nregexp"),
        pytest.param('{ name: { iregexp: "a", inregexp: "^t" } }', ["Alice", "Charlie"], id="iregexp-and-inregexp"),
        pytest.param('{ name: { regexp: "" } }', _ALL_USERS, id="regexp-empty"),
        pytest.param('{ name: { nregexp: "" } }', [], id="nregexp-empty"),
        pytest.param('{ name: { iregexp: "" } }', _ALL_USERS, id="iregexp-empty"),
        pytest.param('{ name: { inregexp: "" } }', [], id="inregexp-empty"),
        pytest.param('{ name: { regexp: null, nregexp: "^B" } }', ["Alice", "Charlie", "Tango"], id="regexp-null"),
        pytest.param('{ name: { regexp: "^B", nregexp: null } }', ["Bob"], id="nregexp-null"),
        pytest.param(
            '{ _not: { name: { regexp: "o", nregexp: "^B" } } }',
            ["Alice", "Bob", "Charlie"],
            id="not-regexp-and-nregexp",
        ),
    ],
)
async def test_regexp_operators_are_independent(
    dto_filter: str, names: list[str], any_async_query: AnyQueryExecutor
) -> None:
    """Test that each regexp operator gets its own predicate, an empty pattern matching every string."""
    result = await maybe_async(any_async_query(f"{{ users(filter: {dto_filter}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names


@pytest.mark.parametrize(
    ("dto_filter", "names"),
    [
        pytest.param('{ name: { iregexp: "^A" } }', ["Alice"], id="iregexp-uppercase"),
        pytest.param('{ name: { iregexp: "^a" } }', ["Alice"], id="iregexp-lowercase"),
        pytest.param('{ name: { iregexp: "lI" } }', ["Alice", "Charlie"], id="iregexp-mixed-case"),
        pytest.param('{ name: { iregexp: "^[A-B]" } }', ["Alice", "Bob"], id="iregexp-uppercase-class"),
        pytest.param('{ name: { iregexp: "^[a-b]" } }', ["Alice", "Bob"], id="iregexp-lowercase-class"),
        pytest.param('{ name: { inregexp: "^A" } }', ["Bob", "Charlie", "Tango"], id="inregexp-uppercase"),
        pytest.param('{ name: { inregexp: "^[B-C]" } }', ["Alice", "Tango"], id="inregexp-uppercase-class"),
        pytest.param('{ _not: { name: { iregexp: "^A" } } }', ["Bob", "Charlie", "Tango"], id="not-iregexp"),
        pytest.param('{ _not: { name: { inregexp: "^A" } } }', ["Alice"], id="not-inregexp"),
        pytest.param('{ name: { iregexp: "E$", regexp: "^A" } }', ["Alice"], id="iregexp-and-regexp"),
        pytest.param('{ name: { iregexp: "E$", nregexp: "^A" } }', ["Charlie"], id="iregexp-and-nregexp"),
        pytest.param('{ name: { regexp: "^[a-z]" } }', [], id="regexp-stays-case-sensitive"),
        pytest.param('{ name: { nregexp: "^[a-z]" } }', _ALL_USERS, id="nregexp-stays-case-sensitive"),
    ],
)
async def test_case_insensitive_regexp_ignores_pattern_case(
    dto_filter: str, names: list[str], any_async_query: AnyQueryExecutor
) -> None:
    """Test that iregexp and inregexp match regardless of the case of either the pattern or the value."""
    result = await maybe_async(any_async_query(f"{{ users(filter: {dto_filter}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names


@pytest.mark.parametrize(
    "user_rows",
    [
        pytest.param(
            [
                {"id": 1, "name": "Émile", "group_id": None, "bio": None},
                {"id": 2, "name": "émile", "group_id": None, "bio": "50%_off"},
                {"id": 3, "name": "Bob", "group_id": None, "bio": "Line one\nline two\n"},
                {"id": 4, "name": "Tango", "group_id": None, "bio": "Tango's bio"},
            ],
            id="non-ascii-names",
        )
    ],
)
@pytest.mark.parametrize(
    ("dto_filter", "names"),
    [
        pytest.param('{ name: { ilike: "é%" } }', ["Émile", "émile"], id="ilike-lowercase"),
        pytest.param('{ name: { ilike: "É%" } }', ["Émile", "émile"], id="ilike-uppercase"),
        pytest.param('{ name: { ilike: "_MILE" } }', ["Émile", "émile"], id="ilike-underscore-wildcard"),
        pytest.param('{ name: { ilike: "é" } }', [], id="ilike-matches-whole-value"),
        pytest.param('{ name: { ilike: "" } }', [], id="ilike-empty"),
        pytest.param('{ name: { nilike: "É%" } }', ["Bob", "Tango"], id="nilike"),
        pytest.param('{ name: { istartswith: "é" } }', ["Émile", "émile"], id="istartswith-lowercase"),
        pytest.param('{ name: { istartswith: "ÉM" } }', ["Émile", "émile"], id="istartswith-uppercase"),
        pytest.param('{ name: { iendswith: "MILE" } }', ["Émile", "émile"], id="iendswith"),
        pytest.param('{ name: { icontains: "É" } }', ["Émile", "émile"], id="icontains-uppercase"),
        pytest.param('{ name: { icontains: "é" } }', ["Émile", "émile"], id="icontains-lowercase"),
        pytest.param('{ name: { icontains: "" } }', ["Bob", "Tango", "Émile", "émile"], id="icontains-empty"),
        pytest.param('{ _not: { name: { ilike: "é%" } } }', ["Bob", "Tango"], id="not-ilike"),
        pytest.param('{ _not: { name: { icontains: "É" } } }', ["Bob", "Tango"], id="not-icontains"),
        pytest.param('{ bio: { ilike: "50%" } }', ["émile"], id="ilike-percent-wildcard"),
        pytest.param('{ bio: { ilike: "5_%_OFF" } }', ["émile"], id="ilike-wildcards-match-literals"),
        pytest.param('{ bio: { ilike: "line%TWO%" } }', ["Bob"], id="ilike-wildcard-spans-newline"),
        pytest.param('{ bio: { ilike: "%two" } }', [], id="ilike-no-match-before-trailing-newline"),
        pytest.param('{ bio: { nilike: "%bio" } }', ["Bob", "émile"], id="nilike-skips-null"),
        pytest.param('{ _not: { bio: { ilike: "%BIO" } } }', ["Bob", "Émile", "émile"], id="not-ilike-null"),
        pytest.param('{ bio: { icontains: "%" } }', ["émile"], id="icontains-literal-percent"),
        pytest.param('{ bio: { icontains: "_" } }', ["émile"], id="icontains-literal-underscore"),
        pytest.param('{ bio: { icontains: "." } }', [], id="icontains-literal-dot"),
        pytest.param('{ bio: { istartswith: "%" } }', [], id="istartswith-literal-percent"),
        pytest.param('{ bio: { iendswith: "%_OFF" } }', ["émile"], id="iendswith-literal-wildcards"),
        pytest.param('{ bio: { iendswith: "TWO" } }', [], id="iendswith-no-match-before-trailing-newline"),
        pytest.param('{ bio: { icontains: "" } }', ["Bob", "Tango", "émile"], id="icontains-empty-skips-null"),
        pytest.param('{ bio: { icontains: "", ilike: null } }', ["Bob", "Tango", "émile"], id="null-ignored"),
    ],
)
async def test_case_insensitive_like_folds_non_ascii(
    dto_filter: str,
    names: list[str],
    any_async_query: AnyQueryExecutor,
    user_rows: RawRecordData,  # noqa: ARG001
) -> None:
    """Test that the case-insensitive LIKE operators ignore the case of non-ASCII letters."""
    result = await maybe_async(any_async_query(f"{{ users(filter: {dto_filter}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names


@pytest.mark.parametrize(
    "user_rows",
    [
        pytest.param(
            [
                {"id": 1, "name": "Alice", "group_id": None, "bio": "a.b (d) [e] +f ^g $h {2} |"},
                {"id": 2, "name": "Bob", "group_id": None, "bio": "axb"},
                {"id": 3, "name": "Charlie", "group_id": None, "bio": "a" * 2000 + "b"},
                {"id": 4, "name": "Tango", "group_id": None, "bio": "a" * 2000},
            ],
            id="regexp-syntax-and-long-bios",
        )
    ],
)
@pytest.mark.parametrize(
    ("dto_filter", "names"),
    [
        pytest.param('{ bio: { ilike: "a.b" } }', [], id="ilike-literal-dot"),
        pytest.param('{ bio: { ilike: "a_b" } }', ["Bob"], id="ilike-underscore"),
        pytest.param('{ bio: { ilike: "A.B%" } }', ["Alice"], id="ilike-literal-dot-prefix"),
        pytest.param('{ bio: { ilike: "%(D)%" } }', ["Alice"], id="ilike-literal-parentheses"),
        pytest.param('{ bio: { ilike: "%[E]%" } }', ["Alice"], id="ilike-literal-brackets"),
        pytest.param('{ bio: { ilike: "%[ab]%" } }', [], id="ilike-no-character-class"),
        pytest.param('{ bio: { ilike: "%+F ^G $H%" } }', ["Alice"], id="ilike-literal-anchors"),
        pytest.param('{ bio: { ilike: "%{2} |" } }', ["Alice"], id="ilike-literal-quantifier-and-bar"),
        pytest.param('{ bio: { nilike: "%(d)%" } }', ["Bob", "Charlie", "Tango"], id="nilike-literal-parentheses"),
        pytest.param('{ bio: { ilike: "%a%a%a%b" } }', ["Charlie"], id="ilike-wildcards-long-value"),
        pytest.param('{ bio: { ilike: "%A%A%A%A%A%C" } }', [], id="ilike-wildcards-long-value-no-match"),
        pytest.param('{ bio: { nilike: "%a%a%a%b" } }', ["Alice", "Bob", "Tango"], id="nilike-wildcards-long-value"),
    ],
)
async def test_ilike_patterns_on_regexp_syntax_and_long_values(
    dto_filter: str,
    names: list[str],
    any_async_query: AnyQueryExecutor,
    user_rows: RawRecordData,  # noqa: ARG001
) -> None:
    """Test that ilike and nilike read regular expression syntax literally and stay fast on long values."""
    result = await maybe_async(any_async_query(f"{{ users(filter: {dto_filter}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names


@pytest.mark.parametrize(
    "user_rows",
    [
        pytest.param(
            [
                {"id": 1, "name": "Alice", "group_id": None, "bio": "50%"},
                {"id": 2, "name": "Bob", "group_id": None, "bio": "50\\%"},
                {"id": 3, "name": "Charlie", "group_id": None, "bio": "a_b"},
                {"id": 4, "name": "Tango", "group_id": None, "bio": "axb"},
            ],
            id="escaped-wildcards",
        )
    ],
)
@pytest.mark.parametrize(
    ("operator", "value", "names"),
    [
        pytest.param("like", r"50\%", ["Alice"], id="like-escaped-percent"),
        pytest.param("ilike", r"50\%", ["Alice"], id="ilike-escaped-percent"),
        pytest.param("nlike", r"50\%", ["Bob", "Charlie", "Tango"], id="nlike-escaped-percent"),
        pytest.param("nilike", r"50\%", ["Bob", "Charlie", "Tango"], id="nilike-escaped-percent"),
        pytest.param("like", r"50\\%", ["Bob"], id="like-escaped-backslash"),
        pytest.param("ilike", r"50\\%", ["Bob"], id="ilike-escaped-backslash"),
        pytest.param("nlike", r"50\\%", ["Alice", "Charlie", "Tango"], id="nlike-escaped-backslash"),
        pytest.param("nilike", r"50\\%", ["Alice", "Charlie", "Tango"], id="nilike-escaped-backslash"),
        pytest.param("like", r"a\_b", ["Charlie"], id="like-escaped-underscore"),
        pytest.param("ilike", r"A\_B", ["Charlie"], id="ilike-escaped-underscore"),
        pytest.param("nlike", r"a\_b", ["Alice", "Bob", "Tango"], id="nlike-escaped-underscore"),
        pytest.param("nilike", r"A\_B", ["Alice", "Bob", "Tango"], id="nilike-escaped-underscore"),
        pytest.param("like", r"\a\x\b", ["Tango"], id="like-escaped-literal"),
        pytest.param("ilike", r"\A_\B", ["Charlie", "Tango"], id="ilike-escaped-literal"),
        pytest.param("like", r"%\\%", ["Bob"], id="like-escaped-backslash-inside"),
        pytest.param("like", r"50\%%", ["Alice"], id="like-escaped-then-wildcard"),
        pytest.param("startswith", "50%", ["Alice"], id="startswith-literal-percent"),
        pytest.param("startswith", "50\\", ["Bob"], id="startswith-literal-backslash"),
        pytest.param("endswith", r"\%", ["Bob"], id="endswith-literal-backslash"),
        pytest.param("contains", "_", ["Charlie"], id="contains-literal-underscore"),
        pytest.param("contains", "\\", ["Bob"], id="contains-literal-backslash"),
        pytest.param("icontains", r"\%", ["Bob"], id="icontains-literal-backslash"),
        pytest.param("istartswith", r"50\\", [], id="istartswith-literal-backslashes"),
        pytest.param("iendswith", "_B", ["Charlie"], id="iendswith-literal-underscore"),
    ],
)
async def test_like_backslash_escapes_next_character(
    operator: str,
    value: str,
    names: list[str],
    any_async_query: AnyQueryExecutor,
    user_rows: RawRecordData,  # noqa: ARG001
) -> None:
    """Test that a backslash escapes the next LIKE pattern character, and that the literal operators read it as is."""
    result = await maybe_async(
        any_async_query(f"{{ users(filter: {{ bio: {{ {operator}: {json.dumps(value)} }} }}) {{ name }} }}")
    )
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names


@pytest.mark.parametrize(
    "user_rows",
    [
        pytest.param(
            [
                {"id": 1, "name": "Émile", "group_id": None, "bio": "ABC"},
                {"id": 2, "name": "émile", "group_id": None, "bio": "abc"},
                {"id": 3, "name": "Bob", "group_id": None, "bio": "ABC "},
                {"id": 4, "name": "Tango", "group_id": None, "bio": None},
            ],
            id="mixed-case",
        )
    ],
)
@pytest.mark.parametrize(
    ("dto_filter", "names"),
    [
        pytest.param('{ bio: { like: "ABC" } }', ["Émile"], id="like"),
        pytest.param('{ bio: { like: "abc" } }', ["émile"], id="like-lowercase"),
        pytest.param('{ bio: { like: "a%c" } }', ["émile"], id="like-wildcard"),
        pytest.param('{ bio: { like: "A_C" } }', ["Émile"], id="like-underscore"),
        pytest.param('{ bio: { nlike: "abc" } }', ["Bob", "Émile"], id="nlike"),
        pytest.param('{ bio: { startswith: "ab" } }', ["émile"], id="startswith"),
        pytest.param('{ bio: { endswith: "bc" } }', ["émile"], id="endswith"),
        pytest.param('{ bio: { contains: "b" } }', ["émile"], id="contains"),
        pytest.param('{ bio: { contains: "B" } }', ["Bob", "Émile"], id="contains-uppercase"),
        pytest.param('{ name: { like: "é%" } }', ["émile"], id="like-non-ascii"),
        pytest.param('{ name: { startswith: "É" } }', ["Émile"], id="startswith-non-ascii"),
        pytest.param('{ name: { like: "_mile" } }', ["Émile", "émile"], id="like-underscore-non-ascii"),
        pytest.param('{ name: { like: "emile" } }', [], id="like-accent"),
        pytest.param('{ bio: { ilike: "abc" } }', ["Émile", "émile"], id="ilike"),
        pytest.param('{ bio: { nilike: "abc" } }', ["Bob"], id="nilike"),
        pytest.param('{ bio: { istartswith: "AB" } }', ["Bob", "Émile", "émile"], id="istartswith"),
        pytest.param('{ bio: { iendswith: "BC" } }', ["Émile", "émile"], id="iendswith"),
        pytest.param('{ bio: { icontains: "B" } }', ["Bob", "Émile", "émile"], id="icontains"),
        pytest.param('{ name: { ilike: "emile" } }', [], id="ilike-accent"),
        pytest.param('{ name: { icontains: "EMI" } }', [], id="icontains-accent"),
        pytest.param('{ bio: { like: "ABC " } }', ["Bob"], id="like-trailing-space"),
        pytest.param('{ bio: { endswith: "C" } }', ["Émile"], id="endswith-trailing-space"),
    ],
)
async def test_case_sensitive_like_operators(
    dto_filter: str,
    names: list[str],
    any_async_query: AnyQueryExecutor,
    user_rows: RawRecordData,  # noqa: ARG001
) -> None:
    """Test that like, nlike, startswith, endswith and contains compare letter case, and trailing spaces, exactly."""
    result = await maybe_async(any_async_query(f"{{ users(filter: {dto_filter}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names
