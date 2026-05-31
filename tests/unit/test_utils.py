from __future__ import annotations

from typing import Optional, Union
from unittest.mock import Mock

import pytest

from strawchemy.exceptions import SessionNotFoundError
from strawchemy.utils.annotation import inner_types
from strawchemy.utils.strawberry import default_session_getter


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
