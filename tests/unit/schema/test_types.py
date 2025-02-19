from __future__ import annotations

from strawchemy import strawchemy

from strawberry import auto
from tests.models import User


def test_type_instance() -> None:
    @strawchemy.type(User)
    class UserType:
        id: auto
        name: auto

    user = UserType(id=1, name="user")
    assert user.id == 1
    assert user.name == "user"


def test_type_instance_auto_as_str() -> None:
    @strawchemy.type(User)
    class UserType:
        id: "auto"
        name: "auto"

    user = UserType(id=1, name="user")
    assert user.id == 1
    assert user.name == "user"
