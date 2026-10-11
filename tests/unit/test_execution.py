"""Tests for root field classification and grouping."""

from __future__ import annotations

import asyncio
import inspect
import warnings
from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from strawberry.types.field import StrawberryField

from strawchemy.execution import RootGroup, StrawchemyExecutionContext
from tests.unit.models import Color

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from strawchemy import Strawchemy
    from strawchemy.execution import RootKind


def _resolver() -> list[int]:
    return []


@pytest.mark.parametrize(
    ("kinds", "expected"),
    [
        (["read", "read", "read"], [RootGroup(True, range(3))]),
        (["write", "write"], [RootGroup(False, range(1)), RootGroup(False, range(1, 2))]),
        (
            ["write", "read", "read", "write"],
            [RootGroup(False, range(1)), RootGroup(True, range(1, 3)), RootGroup(False, range(3, 4))],
        ),
        (
            ["read", "barrier", "read"],
            [RootGroup(True, range(1)), RootGroup(False, range(1, 2)), RootGroup(True, range(2, 3))],
        ),
        ([], []),
    ],
)
def test_group_roots(kinds: list[RootKind], expected: list[RootGroup]) -> None:
    """Test that consecutive reads are grouped and every other root stands alone."""
    assert StrawchemyExecutionContext.group_roots(kinds) == expected


def test_auto_resolved_root_is_read(strawchemy: Strawchemy) -> None:
    """Test that an auto-resolved strawchemy root field is a read."""
    assert StrawchemyExecutionContext.classify_root(strawchemy.field()) == "read"


def test_mutation_field_is_write(strawchemy: Strawchemy) -> None:
    """Test that a strawchemy mutation field is a write."""

    @strawchemy.create_input(Color, include="all")
    class ColorInput: ...

    assert StrawchemyExecutionContext.classify_root(strawchemy.create(ColorInput)) == "write"


def test_custom_resolver_is_barrier(strawchemy: Strawchemy) -> None:
    """Test that a strawchemy field with an unmarked custom resolver is a barrier."""
    assert StrawchemyExecutionContext.classify_root(strawchemy.field(resolver=_resolver)) == "barrier"


def test_read_only_custom_resolver_is_read(strawchemy: Strawchemy) -> None:
    """Test that a custom resolver marked read_only is a read."""
    assert StrawchemyExecutionContext.classify_root(strawchemy.field(resolver=_resolver, read_only=True)) == "read"


def test_strawberry_field_is_barrier() -> None:
    """Test that a plain strawberry field is a barrier."""
    assert StrawchemyExecutionContext.classify_root(StrawberryField()) == "barrier"


def test_missing_field_is_barrier() -> None:
    """Test that a field without a strawberry definition is a barrier."""
    assert StrawchemyExecutionContext.classify_root(None) == "barrier"


def test_sync_execution_runs_read_groups_synchronously(strawchemy: Strawchemy) -> None:
    """Test that execute_sync of a mutation with grouped sync reads returns data without warnings."""

    @strawberry.type
    class Query:
        x: int = 1

    @strawberry.type
    class Mutation:
        @strawchemy.field(read_only=True)
        def a(self) -> int:
            return 1

        @strawchemy.field(read_only=True)
        def b(self) -> int:
            return 1

        @strawberry.field
        def c(self) -> int:
            return 1

        @strawchemy.field(read_only=True)
        def d(self) -> int:
            return 1

    schema = strawberry.Schema(query=Query, mutation=Mutation, execution_context_class=StrawchemyExecutionContext)

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        result = schema.execute_sync("mutation { a b c d }")

    assert not result.errors
    assert result.data == {"a": 1, "b": 1, "c": 1, "d": 1}


def _merge(results: dict[str, Any], key: str) -> dict[str, Any]:
    results[key] = len(results)
    return results


def test_reduce_in_order_sync_returns_dict() -> None:
    """Test that groups returning dicts are merged in order into a plain dict, without a coroutine."""
    result = StrawchemyExecutionContext.reduce_in_order(_merge, ["a", "b", "c"], {})

    assert isinstance(result, dict)
    assert result == {"a": 0, "b": 1, "c": 2}
    assert list(result) == ["a", "b", "c"]


async def test_reduce_in_order_awaitable_in_the_middle() -> None:
    """Test that an awaitable group switches to async and later groups only run once it resolved."""
    events: list[str] = []
    release = asyncio.Event()

    async def slow(results: dict[str, Any]) -> dict[str, Any]:
        events.append("slow-start")
        await release.wait()
        events.append("slow-end")
        return _merge(results, "b")

    def reducer(results: dict[str, Any], key: str) -> dict[str, Any] | Awaitable[dict[str, Any]]:
        events.append(f"run-{key}")
        return slow(results) if key == "b" else _merge(results, key)

    pending = StrawchemyExecutionContext.reduce_in_order(reducer, ["a", "b", "c"], {})
    assert asyncio.iscoroutine(pending)

    task = asyncio.ensure_future(pending)
    await asyncio.sleep(0)
    assert events == ["run-a", "run-b", "slow-start"]

    release.set()
    assert await task == {"a": 0, "b": 1, "c": 2}
    assert events == ["run-a", "run-b", "slow-start", "slow-end", "run-c"]


def test_reduce_in_order_sync_error_stops_later_groups() -> None:
    """Test that an exception raised by a sync group propagates and later groups do not run."""
    ran: list[str] = []

    def reducer(results: dict[str, Any], key: str) -> dict[str, Any]:
        ran.append(key)
        if key == "b":
            msg = "boom"
            raise ValueError(msg)
        return _merge(results, key)

    with pytest.raises(ValueError, match="boom"):
        StrawchemyExecutionContext.reduce_in_order(reducer, ["a", "b", "c"], {})

    assert ran == ["a", "b"]


async def test_reduce_in_order_async_error_stops_later_groups() -> None:
    """Test that an exception raised after switching to async propagates and later groups do not run."""
    ran: list[str] = []

    async def fail() -> dict[str, Any]:
        msg = "boom"
        raise ValueError(msg)

    def reducer(results: dict[str, Any], key: str) -> dict[str, Any] | Awaitable[dict[str, Any]]:
        ran.append(key)
        if key == "a":
            return asyncio.sleep(0, _merge(results, key))
        if key == "b":
            return fail()
        return _merge(results, key)

    pending = StrawchemyExecutionContext.reduce_in_order(reducer, ["a", "b", "c", "d"], {})
    assert inspect.isawaitable(pending)
    with pytest.raises(ValueError, match="boom"):
        await pending

    assert ran == ["a", "b"]
