from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, ForwardRef, get_args, get_origin

from strawberry.types.field import StrawberryField

from strawchemy.exceptions import ScopeConflictError

if TYPE_CHECKING:
    from collections.abc import Hashable

__all__ = ("TypeIdentityCache", "shape_key")

_FIELD_OPTIONS = ("_pagination", "_order_by", "_distinct_on", "_filter")


class TypeIdentityCache:
    """Decides when two type requests yield the same type, shared by every factory of a mapper.

    Factories key requests on what they build from; a generated type of the same name and shape as an earlier
    one is reused for it. Schema-scoped declarations are held by scope key: a generated request of that scope
    gets the declaration instead of a type of its own.
    """

    def __init__(self) -> None:
        self._types: dict[Hashable, Any] = {}
        self._shapes: dict[Hashable, Any] = {}
        self._scoped: dict[Hashable, Any] = {}
        self._scoped_names: dict[Hashable, str] = {}

    def get(self, key: Hashable) -> Any | None:
        return self._types.get(key)

    def set(self, key: Hashable, type_: Any) -> None:
        self._types[key] = type_

    def canonical(self, kind: Hashable, name: str, type_: type[Any]) -> Any:
        """Return the type of the same kind, name and shape generated before `type_`, or `type_` if none was."""
        key = (kind, name, getattr(type_, "__dto_model__", None), shape_key(type_))
        return self._shapes.setdefault(key, type_)

    def stand_in(self, scope_key: Hashable) -> Any | None:
        return self._scoped.get(scope_key)

    def scoped_name(self, scope_key: Hashable) -> str | None:
        return self._scoped_names.get(scope_key)

    def claim_scope(self, scope_key: Hashable, name: str, declaration: type[Any], model: type[Any]) -> None:
        """Reserve the schema scope for the declaration about to be built under `name`.

        Raises:
            ScopeConflictError: If another declaration already holds the scope.
        """
        if (scoped := self._scoped.get(scope_key)) is not None:
            msg = (
                f"{_origin(declaration, model)} cannot declare the schema scope: "
                f"{_origin(scoped, model)} already declares it for the same model and kind"
            )
            raise ScopeConflictError(msg)
        self._scoped_names[scope_key] = name

    def declare_scope(self, scope_key: Hashable, type_: Any) -> None:
        self._scoped[scope_key] = type_


def shape_key(type_: type[Any]) -> Hashable:
    """Return what a generated type exposes, two types of equal shape being interchangeable."""
    if issubclass(type_, Enum):
        return ("enum", tuple((member.name, getattr(member.value, "model_field_name", None)) for member in type_))
    shape = []
    for name, annotation in vars(type_).get("__annotations__", {}).items():
        if name.startswith("__"):
            continue
        value = vars(type_).get(name)
        value_key = _field_key(value) if isinstance(value, StrawberryField) else repr(value)
        shape.append((name, _type_key(annotation), value_key))
    return ("class", tuple(shape))


def _class_key(class_: type[Any]) -> Hashable:
    # Generated types compare by name: registered ones hold a unique name, and the type a cycle
    # points back to is not registered yet, so it compares by the name it was requested under.
    if definition := vars(class_).get("__strawberry_definition__") or vars(class_).get("_enum_definition"):
        return ("named", definition.name)
    if "__dto_model__" in vars(class_):
        return ("named", class_.__name__)
    return ("class", id(class_))


def _type_key(annotation: Any) -> Hashable:
    if isinstance(annotation, type):
        return _class_key(annotation)
    if isinstance(annotation, (ForwardRef, str)):
        return ("named", annotation.__forward_arg__ if isinstance(annotation, ForwardRef) else annotation)
    if (origin := get_origin(annotation)) is not None:
        return (_type_key(origin), tuple(_type_key(arg) for arg in get_args(annotation)))
    return ("repr", repr(annotation))


def _field_key(field: StrawberryField) -> Hashable:
    return (
        type(field),
        field.graphql_name,
        repr(field.default),
        repr(field.default_factory),
        field.description,
        field.deprecation_reason,
        tuple(repr(directive) for directive in field.directives),
        getattr(field, "is_root_field", None),
        tuple(_type_key(getattr(field, option, None)) for option in _FIELD_OPTIONS),
    )


def _origin(type_: type[Any], model: type[Any]) -> str:
    return f"`{type_.__module__}.{type_.__qualname__}` (model `{model.__name__}`)"
