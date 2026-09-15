import pytest

from strawchemy import Strawchemy
from strawchemy.exceptions import EmptyDTOError
from tests.unit.models import Fruit


def test_upsert_conflict_fields_honors_include() -> None:
    strawchemy = Strawchemy("sqlite")

    @strawchemy.upsert_conflict_fields(Fruit, include=["name", "color_id"])
    class ConflictFields: ...

    assert [field.name for field in ConflictFields] == ["nameAndColorId"]


def test_upsert_conflict_fields_rejects_partial_constraint_include() -> None:
    strawchemy = Strawchemy("sqlite")

    with pytest.raises(EmptyDTOError):

        @strawchemy.upsert_conflict_fields(Fruit, include=["name"])
        class ConflictFields: ...



def test_upsert_conflict_fields_rejects_empty_include() -> None:
    strawchemy = Strawchemy("sqlite")

    with pytest.raises(EmptyDTOError):

        @strawchemy.upsert_conflict_fields(Fruit, include=[])
        class ConflictFields: ...

def test_upsert_conflict_fields_honors_exclude() -> None:
    strawchemy = Strawchemy("sqlite")

    @strawchemy.upsert_conflict_fields(Fruit, include="all", exclude=["name"])
    class ConflictFields: ...

    assert [field.name for field in ConflictFields] == ["id"]


def test_upsert_conflict_fields_default_includes_all_constraints() -> None:
    strawchemy = Strawchemy("sqlite")

    @strawchemy.upsert_conflict_fields(Fruit)
    class ConflictFields: ...

    assert [field.name for field in ConflictFields] == ["id", "nameAndColorId"]
