from __future__ import annotations

import dataclasses
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, Literal, Self, TypeAlias, TypeVar, overload

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

__all__ = ("IterationMode", "MatchOn", "Node", "NodeGraphMetadata", "NodeMetadataT", "NodeValueT")

T = TypeVar("T")
NodeValueT = TypeVar("NodeValueT", bound=Any)
NodeMetadataT = TypeVar("NodeMetadataT", bound=Any)
AnyNode = TypeVar("AnyNode", bound="Node[Any, Any]")
MatchOn: TypeAlias = Literal["value_identity", "value_equality", "node_identity"]
IterationMode: TypeAlias = Literal["breadth_first", "depth_first"]


class GraphError(Exception): ...


class UndefinedType: ...


@dataclass
class NodeGraphMetadata:
    count: int = 0


undefined = UndefinedType()


def merge_trees(
    first: AnyNode,
    other: AnyNode,
    match_on: MatchOn | Callable[[AnyNode, AnyNode], bool],
    _merged: AnyNode | None = None,
) -> AnyNode:
    """Merge other into first.

    First tree if copied, then each node in other not present
    in first are added to the latter

    Args:
        first: Base tree
        other: The tree to merge
        match_on: Node matching condition
        _merged: Current merging node. Defaults to None.

    Returns:
        A new tree, with other merge into first
    """
    if not first.match_nodes(first, first, match_on):
        return first
    node = _merged if _merged else first.copy()
    # merge matching children between first and other
    for i, first_child in enumerate(first.children):
        for other_child in other.children:
            if first.match_nodes(other_child, first_child, match_on):
                merge_trees(first_child, other_child, match_on, node.children[i])
    # Add other children not matching any first ones
    for other_child in other.children:
        if not any(child.match_nodes(child, other_child, match_on) for child in first.children):
            node.insert_node(dataclasses.replace(other_child))

    return node


@dataclass
class Node(Generic[NodeValueT, NodeMetadataT]):
    """Very minimalist implementation of a direct graph."""

    value: NodeValueT
    metadata: NodeMetadataT | UndefinedType = undefined
    parent: Self | None = None
    insert_order: int = field(default_factory=int)
    children: list[Self] = field(default_factory=list)
    graph_metadata: NodeGraphMetadata = field(default_factory=NodeGraphMetadata)
    _root: Self = field(init=False)
    _level: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        """Initialize node level and root after instance creation.

        This method is automatically called after the dataclass is initialized.
        It sets the node's level based on its parent's level (if it has a parent)
        and establishes the root node reference.
        """
        if self.parent:
            self._level = self.parent.level + 1
            self._root = self.parent.root
        else:
            self._root = self

    def _iter(self, search_mode: IterationMode) -> Generator[Self, None, None]:
        """Internal iterator that yields nodes based on the specified search mode.

        Args:
            search_mode: The iteration strategy to use ('depth_first' or 'breadth_first')

        Yields:
            Nodes in the order specified by search_mode
        """
        generator = self.iter_depth_first if search_mode == "depth_first" else self.iter_breadth_first
        yield from generator()

    @property
    def root(self) -> Self:
        """Get the root node of the graph.

        Returns:
            The root node of the graph. If this node is the root, returns self.
        """
        return self._root

    @property
    def is_root(self) -> bool:
        """Return True if this node does not have a parent."""
        return self.parent is None

    @property
    def level(self) -> int:
        """Get the level of this node in the graph.

        The root node is at level 0, its children at level 1, etc.

        Returns:
            The level of this node in the graph hierarchy
        """
        return self._level

    def _new(
        self, value: NodeValueT, metadata: NodeMetadataT | UndefinedType = undefined, parent: Self | None = None
    ) -> Self:
        """Create a new node instance with the same graph metadata.

        Args:
            value: The value for the new node
            metadata: Optional metadata for the new node
            parent: Optional parent node reference

        Returns:
            A new node instance with incremented insert order
        """
        return self.__class__(
            value,
            parent=parent,
            metadata=metadata,
            graph_metadata=self.graph_metadata,
            insert_order=self.graph_metadata.count + 1,
        )

    @classmethod
    def match_nodes(cls, left: Self, right: Self, match_on: MatchOn | Callable[[Self, Self], bool]) -> bool:
        """Compare two nodes based on a matching condition.

        Args:
            left: First node to compare
            right: Second node to compare
            match_on: Matching condition. Can be:
                - A callable taking two nodes and returning a boolean
                - 'node_identity': Compare node references (is)
                - 'value_equality': Compare node values (==)
                - 'value_identity': Compare node value references (is)

        Returns:
            True if nodes match according to the condition, False otherwise
        """
        if callable(match_on):
            return match_on(left, right)
        if match_on == "node_identity":
            return left is right
        if match_on == "value_equality":
            return left.value == right.value
        return left.value is right.value

    def insert_child(self, value: NodeValueT, metadata: NodeMetadataT | UndefinedType = undefined) -> Self:
        """Add a new child with the given value to this node.

        Args:
            value: The value with which to create the node
            metadata: node metadata
            key: node key

        Returns:
            The newly created child
        """
        node = self._new(value=value, metadata=metadata, parent=self)
        self.children.append(node)
        self.graph_metadata.count += 1
        return node

    def insert_node(self, child: Self) -> Self:
        """Insert an existing node as a child of this node.

        Creates a copy of the given node with updated graph metadata, parent reference,
        and insert order, then adds it to this node's children.

        Args:
            child: The node to insert as a child

        Returns:
            A copy of the inserted node with updated metadata
        """
        copy = dataclasses.replace(
            child, graph_metadata=self.graph_metadata, parent=self, insert_order=self.graph_metadata.count + 1
        )
        self.children.append(copy)
        self.graph_metadata.count += 1
        return copy

    def upsert_child(
        self,
        value: NodeValueT,
        metadata: NodeMetadataT | UndefinedType = undefined,
        match_on: MatchOn | Callable[[Self, Self], bool] = "node_identity",
    ) -> tuple[Self, bool]:
        """Insert a new child node if no matching child exists, otherwise return the existing one.

        Args:
            value: The value for the new node
            metadata: Optional metadata for the new node
            match_on: The condition used to match existing children. Can be either
                a predefined matching strategy ('value_identity', 'value_equality',
                'node_identity') or a custom function that takes two nodes and returns
                a boolean.

        Returns:
            A tuple containing:
            - The matched or newly created child node
            - A boolean indicating whether a new node was created (True) or an existing one was found (False)
        """
        new_node = self._new(value=value, metadata=metadata)
        if child := next((child for child in self.children if self.match_nodes(child, new_node, match_on)), None):
            return child, False
        return self.insert_child(value, metadata), True

    def iter_parents(self) -> Generator[Self, None, None]:
        """Iterate over node parents until reaching root node.

        Yields:
            Parent nodes
        """
        if self.parent:
            yield self.parent
            yield from self.parent.iter_parents()

    def iter_depth_first(self) -> Generator[Self, None, None]:
        """Iterate over children all in this subtree.

        Yields:
            Children nodes
        """
        for child in self.children:
            yield child
            yield from child.iter_depth_first()

    def iter_breadth_first(self) -> Generator[Self, None, None]:
        """Iterate over all nodes in this subtree using breadth-first traversal.

        In breadth-first traversal, all nodes at the current level are visited
        before moving to nodes at the next level.

        Yields:
            Nodes in breadth-first order
        """
        queue: deque[Self] = deque(self.children)
        while queue:
            child = queue.popleft()
            yield child
            queue.extend(child.children)

    def leaves(self, iteration_mode: IterationMode = "depth_first") -> Generator[Self, None, None]:
        """Iterate over all leaf nodes in the subtree.

        A leaf node is a node that has no children.

        Args:
            iteration_mode: The traversal strategy to use ('depth_first' or 'breadth_first')

        Yields:
            Leaf nodes in the order specified by iteration_mode
        """
        for child in self._iter(iteration_mode):
            if not child.children:
                yield child

    def path_from_root(self) -> list[Self]:
        """Get the path from the root node to this node.

        Returns:
            A list of nodes representing the path from root to this node,
            including both the root and this node
        """
        return [*reversed(list(self.iter_parents())), self]

    @classmethod
    def common_path(
        cls, left: list[Self], right: list[Self], match_on: MatchOn | Callable[[Self, Self], bool] = "node_identity"
    ) -> list[Self]:
        """Find the common path between two lists of nodes.

        Compares nodes at the same positions in both lists using the specified matching condition.
        Stops at the first non-matching pair of nodes.

        Args:
            left: First list of nodes
            right: Second list of nodes
            match_on: The condition used to match nodes. Can be either
                a predefined matching strategy ('value_identity', 'value_equality',
                'node_identity') or a custom function that takes two nodes and returns
                a boolean.

        Returns:
            A list of nodes that form the common path between the two input lists
        """
        common: list[Self] = []
        longest, shortest = (left, right) if len(left) > len(right) else (right, left)
        if len(shortest) == 0:
            return longest
        for i, longest_value in enumerate(longest):
            if i >= len(shortest):
                break
            if cls.match_nodes(longest_value, shortest[i], match_on):
                common.append(longest_value)
        return common

    def copy(self) -> Self:
        """Create a deep copy of this node and its subtree.

        Creates a new node with the same value, metadata, and graph metadata,
        then recursively copies all children.

        Returns:
            A new node that is a deep copy of this node and its subtree
        """
        node = dataclasses.replace(self, children=[])
        for child in self.children:
            node.insert_node(child.copy())
        return node

    @overload
    def find_parent(self, func: Callable[[Self], bool], strict: Literal[True]) -> Self: ...

    @overload
    def find_parent(self, func: Callable[[Self], bool], strict: Literal[False]) -> Self | None: ...

    @overload
    def find_parent(self, func: Callable[[Self], bool], strict: bool = False) -> Self | None: ...

    def find_parent(self, func: Callable[[Self], bool], strict: bool = False) -> Self | None:
        """Find the first parent node that satisfies a given condition.

        Args:
            func: A function that takes a node and returns True if it matches the search criteria
            strict: If True, raises GraphError when no matching parent is found

        Returns:
            The first parent node for which func returns True, or None if no match is found
            and strict is False

        Raises:
            GraphError: If strict is True and no matching parent is found
        """
        for parent in self.iter_parents():
            if func(parent):
                return parent
        if strict:
            msg = "Parent not found"
            raise GraphError(msg)
        return None

    @overload
    def find_child(
        self, func: Callable[[Self], bool], strict: Literal[True], iteration_mode: IterationMode = "depth_first"
    ) -> Self: ...

    @overload
    def find_child(
        self, func: Callable[[Self], bool], strict: Literal[False], iteration_mode: IterationMode = "depth_first"
    ) -> Self | None: ...

    @overload
    def find_child(
        self, func: Callable[[Self], bool], strict: bool = False, iteration_mode: IterationMode = "depth_first"
    ) -> Self | None: ...

    def find_child(
        self, func: Callable[[Self], bool], strict: bool = False, iteration_mode: IterationMode = "depth_first"
    ) -> Self | None:
        """Find the first child node that satisfies a given condition.

        Args:
            func: A function that takes a node and returns True if it matches the search criteria
            strict: If True, raises GraphError when no matching child is found
            iteration_mode: The traversal strategy to use ('depth_first' or 'breadth_first')

        Returns:
            The first child node for which func returns True, or None if no match is found
            and strict is False

        Raises:
            GraphError: If strict is True and no matching child is found
        """
        for child in self._iter(iteration_mode):
            if func(child):
                return child
        if strict:
            msg = "Child not found"
            raise GraphError(msg)
        return None

    def merge_same_children(self, match_on: MatchOn | Callable[[Self, Self], bool]) -> Self:
        """Create a new node by merging children that match according to the given condition.

        This method creates a copy of the current node and merges its children that match
        according to the match_on parameter. For each child, if there are existing children
        that match it, they are merged together using the merge_trees function.

        Args:
            match_on: The condition used to determine if two nodes match. Can be either
                a predefined matching strategy ('value_identity', 'value_equality',
                'node_identity') or a custom function that takes two nodes and returns
                a boolean.

        Returns:
            A new node with merged children.
        """
        node = dataclasses.replace(self, children=[])
        for child in self.children:
            child_copy = child.copy()
            existing_children = [child for child in node.children if child.match_nodes(child, child_copy, match_on)]
            for existing_child in existing_children:
                child_copy = merge_trees(existing_child, child_copy, match_on)
            node.insert_node(child_copy)
        return node
