from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from strawchemy import QueryHook
from strawchemy.exceptions import QueryHookError
from tests.unit.models import Color, Fruit

if TYPE_CHECKING:
    from collections.abc import Sequence

    from strawchemy.transpiler.hook import LoadType


class _ClassLoadHook(QueryHook[Fruit]):
    load: Sequence[LoadType] = [Fruit.name, Fruit.color]


class _NestedClassLoadHook(QueryHook[Color]):
    load: Sequence[LoadType] = [Color.name, (Color.fruits, [Fruit.name, (Fruit.color, [Color.name])])]


class _InheritedClassLoadHook(_ClassLoadHook): ...


class _OverridingClassLoadHook(_ClassLoadHook):
    load: Sequence[LoadType] = [Fruit.sweetness]


@dataclass
class _DataclassLoadHook(QueryHook[Fruit]):
    load: Sequence[LoadType] = field(default_factory=lambda: [Fruit.name])


def _resolved_load(hook: QueryHook[Any]) -> tuple[list[Any], list[Any]]:
    return hook._columns, hook._relationships  # noqa: SLF001


def test_default_load_is_empty() -> None:
    """Test that a hook built without ``load`` loads nothing."""
    hook = QueryHook()
    assert hook.load == []
    assert _resolved_load(hook) == ([], [])


def test_instance_load() -> None:
    """Test that ``load`` passed at instantiation splits into columns and relationships."""
    hook = QueryHook(load=[Fruit.name, Fruit.color])
    assert hook.load == [Fruit.name, Fruit.color]
    assert _resolved_load(hook) == ([Fruit.name], [(Fruit.color, [])])


def test_class_load() -> None:
    """Test that a subclass setting ``load`` as a class attribute loads it."""
    hook = _ClassLoadHook()
    assert hook.load == [Fruit.name, Fruit.color]
    assert _resolved_load(hook) == ([Fruit.name], [(Fruit.color, [])])


def test_class_load_nested_relationship() -> None:
    """Test that a class-level ``load`` keeps nested relationship specs."""
    hook = _NestedClassLoadHook()
    assert _resolved_load(hook) == ([Color.name], [(Color.fruits, [Fruit.name, (Fruit.color, [Color.name])])])


def test_instance_load_overrides_class_load() -> None:
    """Test that ``load`` passed at instantiation wins over the class attribute."""
    hook = _ClassLoadHook(load=[Fruit.sweetness])
    assert hook.load == [Fruit.sweetness]
    assert _resolved_load(hook) == ([Fruit.sweetness], [])


def test_empty_instance_load_overrides_class_load() -> None:
    """Test that an explicit empty ``load`` wins over the class attribute."""
    hook = _ClassLoadHook(load=[])
    assert hook.load == []
    assert _resolved_load(hook) == ([], [])


def test_class_load_is_not_shared_between_instances() -> None:
    """Test that instances of a class-level ``load`` hook get their own lists."""
    first, second = _ClassLoadHook(), _ClassLoadHook()
    assert first.load is not second.load
    assert first.load is not _ClassLoadHook.load
    assert all(a is not b for a, b in zip(_resolved_load(first), _resolved_load(second), strict=True))


@pytest.mark.parametrize(
    ("hook_class", "columns", "relationships"),
    [
        pytest.param(_InheritedClassLoadHook, [Fruit.name], [(Fruit.color, [])], id="inherited"),
        pytest.param(_OverridingClassLoadHook, [Fruit.sweetness], [], id="overridden"),
    ],
)
def test_class_load_on_subclass_of_subclass(
    hook_class: type[QueryHook[Fruit]], columns: list[object], relationships: list[object]
) -> None:
    """Test that a subclass of a subclass inherits or overrides the class-level ``load``."""
    hook = hook_class()
    assert _resolved_load(hook) == (columns, relationships)


def test_dataclass_subclass_load_field() -> None:
    """Test that a dataclass subclass redeclaring ``load`` as a field uses its default."""
    hook = _DataclassLoadHook()
    assert hook.load == [Fruit.name]
    assert _resolved_load(hook) == ([Fruit.name], [])
    assert _resolved_load(_DataclassLoadHook(load=[Fruit.sweetness])) == ([Fruit.sweetness], [])


def test_class_load_wrong_relationship_load_spec() -> None:
    """Test that a class-level ``load`` keyed by a column raises ``QueryHookError``."""

    class WrongLoadHook(QueryHook[Fruit]):
        load: Sequence[LoadType] = [(Fruit.name, [Fruit.id])]

    with pytest.raises(
        QueryHookError, match=re.escape("Keys of mappings passed in `load` param must be relationship attributes: ")
    ):
        WrongLoadHook()
