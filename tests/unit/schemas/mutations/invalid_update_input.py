from __future__ import annotations

from strawchemy import Strawchemy

from tests.unit.models import Group

strawchemy = Strawchemy()


@strawchemy.input(Group, "update", exclude={"id"})
class GroupInput: ...
