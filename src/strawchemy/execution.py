"""Execution context running consecutive read root fields of a mutation concurrently."""

from __future__ import annotations

from dataclasses import dataclass
from inspect import isawaitable
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from strawberry.schema.schema import StrawberryGraphQLCoreExecutionContext

from strawchemy.schema.field import StrawchemyField
from strawchemy.schema.mutation.fields import _StrawchemyMutationField

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from graphql import GraphQLObjectType
    from graphql.pyutils import AwaitableOrValue, Path
    from strawberry.types.field import StrawberryField

    _T = TypeVar("_T")
    _I = TypeVar("_I")
    _FieldsExecutor = Callable[..., AwaitableOrValue[dict[str, Any]]]

__all__ = ("RootGroup", "RootKind", "StrawchemyExecutionContext")

RootKind = Literal["read", "write", "barrier"]


@dataclass(frozen=True, slots=True)
class RootGroup:
    """Consecutive root fields executed together."""

    concurrent: bool
    """Whether the fields are gathered rather than executed one after the other."""
    indices: range
    """Positions of the fields in document order."""


class StrawchemyExecutionContext(StrawberryGraphQLCoreExecutionContext):
    """Execution context gathering each run of consecutive read root fields of a mutation."""

    @staticmethod
    async def _reduce_pending(
        reducer: Callable[[_T, _I], _T | Awaitable[_T]], pending: Awaitable[_T], remaining: Sequence[_I]
    ) -> _T:
        accumulator = await pending
        for item in remaining:
            result = reducer(accumulator, item)
            accumulator = await result if isawaitable(result) else result
        return accumulator

    @classmethod
    def _root_kind(cls, parent_type: GraphQLObjectType, field_nodes: Sequence[Any]) -> RootKind:
        node = field_nodes[0]
        node = getattr(node, "node", node)  # graphql-core 3.3 wraps nodes in FieldDetails
        field = parent_type.fields.get(node.name.value)
        return cls.classify_root(field.extensions.get("strawberry-definition") if field is not None else None)

    @staticmethod
    def classify_root(field: StrawberryField | None) -> RootKind:
        """Return whether a root field reads, writes, or must run on its own."""
        if isinstance(field, _StrawchemyMutationField):
            return "write"
        if isinstance(field, StrawchemyField) and (
            field.read_only or (field.is_root_field and field.base_resolver is None)
        ):
            return "read"
        return "barrier"

    @staticmethod
    def group_roots(kinds: Sequence[RootKind]) -> list[RootGroup]:
        """Group consecutive reads into concurrent groups, putting every other root in a serial group of its own."""
        groups: list[RootGroup] = []
        for index, kind in enumerate(kinds):
            if kind == "read" and groups and groups[-1].concurrent:
                groups[-1] = RootGroup(concurrent=True, indices=range(groups[-1].indices.start, index + 1))
            else:
                groups.append(RootGroup(concurrent=kind == "read", indices=range(index, index + 1)))
        return groups

    @classmethod
    def reduce_in_order(
        cls, reducer: Callable[[_T, _I], _T | Awaitable[_T]], items: Sequence[_I], initial: _T
    ) -> _T | Awaitable[_T]:
        """Reduce items in order, staying synchronous until a reducer call returns an awaitable."""
        accumulator = initial
        for position, item in enumerate(items):
            result = reducer(accumulator, item)
            if isawaitable(result):
                return cls._reduce_pending(reducer, result, items[position + 1 :])
            accumulator = result
        return accumulator

    def execute_fields_serially(  # ty: ignore[invalid-method-override]  # spans the graphql-core 3.2 and 3.3 signatures
        self,
        parent_type: GraphQLObjectType,
        source_value: object,
        path: Path | None,
        fields: dict[str, Any],
        *args: object,
    ) -> AwaitableOrValue[dict[str, Any]]:
        """Execute root fields in document order, gathering each run of consecutive reads."""
        items = list(fields.items())
        groups = self.group_roots([self._root_kind(parent_type, field_nodes) for _, field_nodes in items])
        execute_serially = cast("_FieldsExecutor", super().execute_fields_serially)
        if all(len(group.indices) == 1 for group in groups):
            return execute_serially(parent_type, source_value, path, fields, *args)

        def execute_group(results: dict[str, Any], group: RootGroup) -> AwaitableOrValue[dict[str, Any]]:
            execute = cast("_FieldsExecutor", self.execute_fields) if group.concurrent else execute_serially
            group_fields = dict(items[group.indices.start : group.indices.stop])
            group_results = execute(parent_type, source_value, path, group_fields, *args)
            if isinstance(group_results, dict):
                results.update(group_results)
                return results

            async def merge() -> dict[str, Any]:
                results.update(await group_results)
                return results

            return merge()

        return self.reduce_in_order(execute_group, groups, {})
