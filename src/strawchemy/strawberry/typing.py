from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeAlias

from strawberry.experimental.pydantic.conversion_types import PydanticModel, StrawberryTypeFromPydantic
from strawberry.types.base import WithStrawberryObjectDefinition
from strawchemy.graphql.dto import StrawchemyDTOAttributes

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy import Select
    from strawberry import Info
    from strawchemy.sqlalchemy.typing import AnyAsyncSession, AnySyncSession

__all__ = (
    "AnySessionGetter",
    "AsyncSessionGetter",
    "FilterStatementCallable",
    "InputType",
    "StrawchemyTypeFromPydantic",
    "StrawchemyTypeWithStrawberryObjectDefinition",
    "SyncSessionGetter",
)

GraphQLType = Literal["input", "object", "interface", "enum"]
AsyncSessionGetter: TypeAlias = "Callable[[Info[Any, Any]], AnyAsyncSession]"
SyncSessionGetter: TypeAlias = "Callable[[Info[Any, Any]], AnySyncSession]"
AnySessionGetter: TypeAlias = "AsyncSessionGetter | SyncSessionGetter"
FilterStatementCallable: TypeAlias = "Callable[[Info[Any, Any]], Select[tuple[Any]]]"
InputType: TypeAlias = Literal["create", "update_by_pk", "update_by_filter"]


class StrawchemyTypeWithStrawberryObjectDefinition(StrawchemyDTOAttributes, WithStrawberryObjectDefinition): ...


class StrawchemyTypeFromPydantic(StrawchemyDTOAttributes, StrawberryTypeFromPydantic[PydanticModel]): ...
