# ruff: noqa: C901, PLR0912, PLR0915, A001, UP036, SLF001, E731

from __future__ import annotations

import dataclasses
import sys
import warnings
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel

from strawberry.annotation import StrawberryAnnotation
from strawberry.experimental.pydantic._compat import (
    CompatModelField,  # pyright: ignore[reportPrivateImportUsage]
    PydanticCompat,  # pyright: ignore[reportPrivateImportUsage]
    smart_deepcopy,  # pyright: ignore[reportAttributeAccessIssue]
)
from strawberry.experimental.pydantic.conversion import (
    convert_pydantic_model_to_strawberry_class,
    convert_strawberry_class_to_pydantic_model,
)
from strawberry.experimental.pydantic.exceptions import BothDefaultAndDefaultFactoryDefinedError, MissingFieldsListError
from strawberry.experimental.pydantic.object_type import get_type_for_field
from strawberry.experimental.pydantic.utils import (
    DataclassCreationFields,
    ensure_all_auto_fields_in_pydantic,
    get_private_fields,
)
from strawberry.types.auto import StrawberryAuto
from strawberry.types.cast import get_strawberry_type_cast
from strawberry.types.field import StrawberryField
from strawberry.types.object_type import _process_type, _wrap_dataclass
from strawberry.types.type_resolver import _get_fields
from strawberry.types.unset import UNSET

if TYPE_CHECKING:
    import builtins
    from collections.abc import Callable, Sequence

    from graphql import GraphQLResolveInfo
    from strawberry.experimental.pydantic.conversion_types import PydanticModel, StrawberryTypeFromPydantic

    NoArgAnyCallable = Callable[..., Any]

__all__ = ["type"]


def get_default_factory_for_field(
    field: CompatModelField,
    compat: PydanticCompat,
    partial: bool = False,
) -> tuple[bool, NoArgAnyCallable | dataclasses._MISSING_TYPE]:
    """Gets the default factory for a pydantic field.

    Handles mutable defaults when making the dataclass by
    using pydantic's smart_deepcopy

    Returns optionally a NoArgAnyCallable representing a default_factory parameter
    """
    # replace dataclasses.MISSING with our own UNSET to make comparisons easier
    default_factory = field.default_factory if field.has_default_factory else UNSET
    default = field.default if field.has_default else UNSET

    has_factory = default_factory is not None and default_factory is not UNSET
    has_default = default is not None and default is not UNSET

    default = UNSET if has_default and partial else default
    if has_factory:
        if partial:
            default_factory = lambda: UNSET
        if has_default:
            default_factory = cast("NoArgAnyCallable", default_factory)

            raise BothDefaultAndDefaultFactoryDefinedError(default=default, default_factory=default_factory)

        return True, cast("NoArgAnyCallable", default_factory)

    # if we have a default, we should return it

    if has_default:
        # if the default value is a pydantic base model
        # we should return the serialized version of that default for
        # printing the value.
        if isinstance(default, BaseModel):
            return True, lambda: compat.model_dump(default)
        return True, lambda: smart_deepcopy(default)  # pyright: ignore[reportUnknownLambdaType]

    # if we don't have default or default_factory, but the field is not required,
    # we should return a factory that returns None

    if not field.required:
        return False, lambda: None if not partial else UNSET

    return False, dataclasses.MISSING


def _build_dataclass_creation_fields(
    field: CompatModelField,
    is_input: bool,
    existing_fields: dict[str, StrawberryField],
    auto_fields_set: set[str],
    use_pydantic_alias: bool,
    compat: PydanticCompat,
    partial_fields: set[str],
    partial: bool = False,
) -> DataclassCreationFields:
    field_type = (
        get_type_for_field(field, is_input, compat=compat)
        if field.name in auto_fields_set
        else existing_fields[field.name].type
    )

    if field.name in existing_fields and existing_fields[field.name].base_resolver is not None:
        # if the user has defined a resolver for this field, always use it
        strawberry_field = existing_fields[field.name]
    else:
        # otherwise we build an appropriate strawberry field that resolves it
        existing_field = existing_fields.get(field.name)
        graphql_name = None
        if existing_field and existing_field.graphql_name:
            graphql_name = existing_field.graphql_name
        elif field.has_alias and use_pydantic_alias:
            graphql_name = field.alias

        field_is_partial = partial or field.name in partial_fields
        user_defined_default, factory = get_default_factory_for_field(field, compat, field_is_partial)
        if user_defined_default:
            field_type = field_type | None  # pyright: ignore[reportOperatorIssue]

        strawberry_field = StrawberryField(
            python_name=field.name,
            graphql_name=graphql_name,
            # always unset because we use default_factory instead
            default=dataclasses.MISSING,
            default_factory=factory,
            type_annotation=StrawberryAnnotation.from_annotation(field_type),
            description=field.description,
            deprecation_reason=(existing_field.deprecation_reason if existing_field else None),
            permission_classes=(existing_field.permission_classes if existing_field else []),
            directives=existing_field.directives if existing_field else (),
            metadata=existing_field.metadata if existing_field else {},
        )

    return DataclassCreationFields(
        name=field.name,
        field_type=field_type,  # pyright: ignore[reportArgumentType]
        field=strawberry_field,
    )


def type(
    model: builtins.type[PydanticModel],
    *,
    fields: list[str] | None = None,
    name: str | None = None,
    is_input: bool = False,
    is_interface: bool = False,
    description: str | None = None,
    directives: Sequence[object] | None = (),
    all_fields: bool = False,
    include_computed: bool = False,
    use_pydantic_alias: bool = True,
    partial: bool = False,
    partial_fields: set[str] | None = None,
) -> Callable[..., builtins.type[StrawberryTypeFromPydantic[PydanticModel]]]:
    def wrap(cls: Any) -> builtins.type[StrawberryTypeFromPydantic[PydanticModel]]:
        compat = PydanticCompat.from_model(model)
        model_fields = compat.get_model_fields(model, include_computed=include_computed)
        original_fields_set = set(fields) if fields else set()

        if fields:
            warnings.warn(
                "`fields` is deprecated, use `auto` type annotations instead",
                DeprecationWarning,
                stacklevel=2,
            )

        existing_fields = getattr(cls, "__annotations__", {})

        # these are the fields that matched a field name in the pydantic model
        # and should copy their alias from the pydantic model
        fields_set = original_fields_set.union({name for name, _ in existing_fields.items() if name in model_fields})
        # these are the fields that were marked with strawberry.auto and
        # should copy their type from the pydantic model
        auto_fields_set = original_fields_set.union(
            {name for name, type_ in existing_fields.items() if isinstance(type_, StrawberryAuto)}
        )
        partial_fields_set = partial_fields or set()

        if all_fields:
            if fields_set:
                warnings.warn(
                    "Using all_fields overrides any explicitly defined fields in the model, using both is likely a bug",
                    stacklevel=2,
                )
            fields_set = set(model_fields.keys())
            auto_fields_set = set(model_fields.keys())

        if partial and partial_fields_set:
            warnings.warn(
                "Using partial makes all model fields partial, even if partial_fields is set. "
                "Using both is likely a bug",
                stacklevel=2,
            )

        if not fields_set:
            raise MissingFieldsListError(cls)

        ensure_all_auto_fields_in_pydantic(
            model=model,
            auto_fields=auto_fields_set,
            cls_name=cls.__name__,
            include_computed=include_computed,
        )

        wrapped = _wrap_dataclass(cls)
        extra_strawberry_fields = _get_fields(wrapped, {})
        extra_fields = cast("list[dataclasses.Field[Any]]", extra_strawberry_fields)
        private_fields = get_private_fields(wrapped)

        extra_fields_dict = {field.name: field for field in extra_strawberry_fields}

        all_model_fields: list[DataclassCreationFields] = [
            _build_dataclass_creation_fields(
                field,
                is_input,
                extra_fields_dict,
                auto_fields_set,
                use_pydantic_alias,
                compat,
                partial_fields_set,
                partial,
            )
            for field_name, field in model_fields.items()
            if field_name in fields_set
        ]

        all_model_fields = [
            DataclassCreationFields(
                name=field.name,
                field_type=field.type,  # pyright: ignore[reportArgumentType]
                field=field,
            )
            for field in extra_fields + private_fields
            if field.name not in fields_set
        ] + all_model_fields

        # Implicitly define `is_type_of` to support interfaces/unions that use
        # pydantic objects (not the corresponding strawberry type)
        @classmethod
        def is_type_of(cls: builtins.type, obj: Any, _info: GraphQLResolveInfo) -> bool:
            if (type_cast := get_strawberry_type_cast(obj)) is not None:
                return type_cast is cls

            return isinstance(obj, cls | model)

        namespace = {"is_type_of": is_type_of}
        # We need to tell the difference between a from_pydantic method that is
        # inherited from a base class and one that is defined by the user in the
        # decorated class. We want to override the method only if it is
        # inherited. To tell the difference, we compare the class name to the
        # fully qualified name of the method, which will end in <class>.from_pydantic
        has_custom_from_pydantic = hasattr(cls, "from_pydantic") and cls.from_pydantic.__qualname__.endswith(
            f"{cls.__name__}.from_pydantic"
        )
        has_custom_to_pydantic = hasattr(cls, "to_pydantic") and cls.to_pydantic.__qualname__.endswith(
            f"{cls.__name__}.to_pydantic"
        )

        if has_custom_from_pydantic:
            namespace["from_pydantic"] = cls.from_pydantic
        if has_custom_to_pydantic:
            namespace["to_pydantic"] = cls.to_pydantic

        if hasattr(cls, "resolve_reference"):
            namespace["resolve_reference"] = cls.resolve_reference

        kwargs: dict[str, object] = {}

        # Python 3.10.1 introduces the kw_only param to `make_dataclass`.
        # If we're on an older version then generate our own custom init function
        # Note: Python 3.10.0 added the `kw_only` param to dataclasses, it was
        # just missed from the `make_dataclass` function:
        # https://github.com/python/cpython/issues/89961
        if sys.version_info >= (3, 10, 1):
            kwargs["kw_only"] = dataclasses.MISSING
        else:
            kwargs["init"] = False

        cls = dataclasses.make_dataclass(
            cls.__name__,
            [field.to_tuple() for field in all_model_fields],
            bases=cls.__bases__,
            namespace=namespace,
            **kwargs,  # pyright: ignore[reportArgumentType]
        )

        if sys.version_info < (3, 10, 1):
            from strawberry.utils.dataclasses import add_custom_init_fn

            add_custom_init_fn(cls)

        _process_type(
            cls,
            name=name,
            is_input=is_input,
            is_interface=is_interface,
            description=description,
            directives=directives,
        )

        if is_input:
            model._strawberry_input_type = cls
        else:
            model._strawberry_type = cls
        cls._pydantic_type = model

        def from_pydantic_default(
            instance: PydanticModel, extra: dict[str, Any] | None = None
        ) -> StrawberryTypeFromPydantic[PydanticModel]:
            ret = convert_pydantic_model_to_strawberry_class(cls=cls, model_instance=instance, extra=extra)
            ret._original_model = instance
            return ret

        def to_pydantic_default(self: Any, **kwargs: Any) -> PydanticModel:
            instance_kwargs = {
                f.name: convert_strawberry_class_to_pydantic_model(getattr(self, f.name))
                for f in dataclasses.fields(self)
                if getattr(self, f.name) is not UNSET
            }
            instance_kwargs.update(kwargs)
            return model(**instance_kwargs)

        if not has_custom_from_pydantic:
            cls.from_pydantic = staticmethod(from_pydantic_default)
        if not has_custom_to_pydantic:
            cls.to_pydantic = to_pydantic_default

        return cls

    return wrap
