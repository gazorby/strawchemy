"""The columns a level loads from its own node, and the keys identifying the relation objects owning computed values."""

from __future__ import annotations

from typing import TYPE_CHECKING

from strawchemy.dto.inspectors import SQLAlchemyInspector
from strawchemy.transpiler._core.pipeline import PassBase

if TYPE_CHECKING:
    from strawchemy.transpiler._core.level import Level
    from strawchemy.transpiler._core.rowset import Projection, RowSet
    from strawchemy.typing import QueryNodeType

__all__ = ("Selection",)


class Selection(PassBase):
    """Loads the selected columns of the level's node, its primary keys always, and its JSON extractions."""

    def project(self, level: Level, rows: RowSet, projection: Projection) -> Projection:
        selection = level.request.selection
        keys: list[str] = []
        for child in selection.children:
            if child.value.is_relation or child.value.is_computed:
                continue
            if child.metadata.data.is_transform:
                projection = projection.with_computed(child, level.column(child))
            else:
                keys.append(child.value.model_field.key)
        primary_keys = level.primary_keys()
        keys.extend(key for column in primary_keys if (key := column.key) is not None and key not in keys)
        projection = projection.with_loaded(level.node, *keys)
        if level.kind == "relation" and _owns_computed(selection):
            name = _label_name(level.node)
            identity = tuple(column.label(f"{name}__{column.key}") for column in primary_keys)
            projection = projection.with_columns(*identity).with_identity(level.node, identity)
        return projection


def _label_key(node: QueryNodeType) -> str:
    if node.is_root:
        return SQLAlchemyInspector.table_name(node.value.model)
    return node.value.model_field.key if node.value.has_model_field else ""


def _label_name(node: QueryNodeType) -> str:
    """Returns the key of the relation ``node`` prefixed by its parent's, so that labels of two levels differ."""
    assert node.parent is not None, "a relation level has a parent"
    return f"{_label_key(node.parent)}__{_label_key(node)}"


def _owns_computed(node: QueryNodeType) -> bool:
    """Tells whether a computed or transform value belongs to ``node``'s objects, not to those of a relation below."""
    for child in node.children:
        if child.value.is_relation and not child.value.is_computed:
            continue
        if child.value.is_computed or child.metadata.data.is_transform or _owns_computed(child):
            return True
    return False
