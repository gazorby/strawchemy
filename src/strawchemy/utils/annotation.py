from __future__ import annotations

import inspect
import sys
import typing
from typing import Any, ForwardRef, Optional, TypeVar, Union, get_args, get_origin, get_type_hints

from strawchemy.typing import UNION_TYPES

if typing.TYPE_CHECKING:
    from collections.abc import Mapping

T = TypeVar("T", bound="Any")


def non_optional_type_hint(type_hint: Any) -> Any:
    origin, args = get_origin(type_hint), get_args(type_hint)
    if origin is Optional:
        return args
    if origin in UNION_TYPES:
        union_args = tuple([arg for arg in args if arg not in (None, type(None))])
        if len(union_args) == 1:
            return union_args[0]
        return Union[union_args]
    return type_hint


def is_type_hint_optional(type_hint: Any) -> bool:
    """Whether the given type hint is considered as optional or not.

    Returns:
        `True` if arguments of the given type hint are optional

    Three cases are considered:
    ```
        Optional[str]
        Union[str, None]
        str | None
    ```
    In any other form, the type hint will not be considered as optional
    """
    origin = get_origin(type_hint)
    if origin is None:
        return False
    if origin is Optional:
        return True
    if origin in UNION_TYPES:
        args = get_args(type_hint)
        return any(arg is type(None) for arg in args)
    return False


if sys.version_info < (3, 14):

    def get_annotations(obj: Any) -> dict[str, Any]:
        """Get the annotations of the given object."""
        return inspect.get_annotations(obj)

else:
    import annotationlib

    def get_annotations(obj: Any) -> dict[str, Any]:
        """Get the annotations of the given object, keeping undefined names as forward references."""
        return annotationlib.get_annotations(obj, format=annotationlib.Format.FORWARDREF)


def _class_namespaces(owner: type[Any], localns: Mapping[str, Any] | None) -> tuple[dict[str, Any], Mapping[str, Any]]:
    module_ns = getattr(sys.modules.get(owner.__module__), "__dict__", {})
    if localns is None:
        # Same swap as `typing.get_type_hints`: module names take precedence over the class namespace.
        return dict(vars(owner)), module_ns
    return module_ns, localns


def get_type_hints_partial(
    cls: type[Any], localns: Mapping[str, Any] | None = None, include_extras: bool = True
) -> dict[str, Any]:
    """Resolve the type hints of a class, keeping the unresolvable ones as their raw annotation."""
    try:
        return get_type_hints(cls, localns=localns, include_extras=include_extras)
    except NameError:
        pass
    type_hints: dict[str, Any] = {}
    for owner in reversed(cls.__mro__):
        globalns, owner_localns = _class_namespaces(owner, localns)
        for name, annotation in get_annotations(owner).items():
            single = type(owner.__name__, (), {"__module__": owner.__module__, "__annotations__": {name: annotation}})
            try:
                type_hints[name] = get_type_hints(
                    single, globalns=globalns, localns=owner_localns, include_extras=include_extras
                )[name]
            except NameError:
                type_hints[name] = annotation
    return type_hints


def get_origin_or_self(annotation: Any) -> Any:
    """Returns the unsubscripted origin of a parametrized type, or the object itself.

    ``OrderComparison[int]`` -> ``OrderComparison``; ``TextComparison`` -> ``TextComparison``.
    """
    return get_origin(annotation) or annotation


def annotation_name(annotation: Any) -> str:
    """Renders an annotation for an error message, tolerating typing special forms."""
    return getattr(annotation, "__name__", None) or str(annotation)


def inner_types(annotation: Any) -> tuple[Any, ...]:
    """Flatten a generic annotation to its innermost leaf types.

    list[Optional[str]] -> (str, NoneType)
    """
    origin = get_origin(annotation)
    if not origin or not hasattr(annotation, "__args__"):
        return (annotation,)
    arg_types: list[Any] = []
    for arg_type in get_args(annotation):
        arg_types.extend(inner_types(arg_type))
    return tuple(arg_types)


if sys.version_info < (3, 12, 4):

    def _evaluate_forwardref(
        type_: ForwardRef, globalns: dict[str, Any] | None, localns: Mapping[str, Any] | None
    ) -> Any:
        return type_._evaluate(globalns, localns, recursive_guard=frozenset())  # noqa: SLF001

elif sys.version_info < (3, 14):

    def _evaluate_forwardref(
        type_: ForwardRef, globalns: dict[str, Any] | None, localns: Mapping[str, Any] | None
    ) -> Any:
        return type_._evaluate(globalns, localns, type_params=(), recursive_guard=frozenset())  # noqa: SLF001

else:

    def _evaluate_forwardref(
        type_: ForwardRef, globalns: dict[str, Any] | None, localns: Mapping[str, Any] | None
    ) -> Any:
        return typing.evaluate_forward_ref(
            type_,
            globals=globalns,
            locals=localns,
            type_params=(),
            _recursive_guard=set(),
        )


def try_resolve_forwardref(
    ref: str | ForwardRef, globalns: Mapping[str, Any] | None = None, localns: Mapping[str, Any] | None = None
) -> Any | None:
    """Resolve a forward reference (or string annotation) against the given namespaces.

    Args:
        ref: A `ForwardRef`, or a string annotation that is wrapped into one.
        globalns: Global namespace used to look up names while evaluating the reference.
        localns: Local namespace used to look up names while evaluating the reference.

    Returns:
        The resolved type, or `None` if the name cannot be resolved against the namespaces.
    """
    forward = ref if isinstance(ref, ForwardRef) else ForwardRef(ref)
    try:
        return _evaluate_forwardref(forward, globalns=dict(globalns or {}), localns=localns)
    except NameError:
        return None
