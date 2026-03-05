from __future__ import annotations

import pytest

from strawchemy.schema.scalars.base import _parse_hstore


def test_parse_hstore_valid_dict() -> None:
    assert _parse_hstore({"key": "value"}) == {"key": "value"}


def test_parse_hstore_coerces_to_strings() -> None:
    assert _parse_hstore({1: 2}) == {"1": "2"}


@pytest.mark.parametrize(
    ("value", "type_name"),
    [
        ("not a dict", "str"),
        ([1, 2, 3], "list"),
        (42, "int"),
        (None, "NoneType"),
    ],
)
def test_parse_hstore_rejects_non_dict(value: object, type_name: str) -> None:
    with pytest.raises(TypeError, match=f"HStore value must be a dict, got {type_name}"):
        _parse_hstore(value)
