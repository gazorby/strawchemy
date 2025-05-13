from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeAlias

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy import Select
    from strawberry import Info
    from strawberry.experimental.pydantic.conversion_types import PydanticModel, StrawberryTypeFromPydantic
    from strawberry.types.base import WithStrawberryObjectDefinition
    from strawchemy.graphql.dto import StrawchemyDTOAttributes
    from strawchemy.sqlalchemy.typing import AnyAsyncSession, AnySyncSession

__all__ = (
    "AnySessionGetter",
    "AsyncSessionGetter",
    "FilterStatementCallable",
    "StrawchemyTypeFromPydantic",
    "StrawchemyTypeWithStrawberryObjectDefinition",
    "SyncSessionGetter",
)

GraphQLType = Literal["input", "object", "interface", "enum"]
AsyncSessionGetter: TypeAlias = "Callable[[Info[Any, Any]], AnyAsyncSession]"
SyncSessionGetter: TypeAlias = "Callable[[Info[Any, Any]], AnySyncSession]"
AnySessionGetter: TypeAlias = "AsyncSessionGetter | SyncSessionGetter"
FilterStatementCallable: TypeAlias = "Callable[[Info[Any, Any]], Select[tuple[Any]]]"


if TYPE_CHECKING:

    class StrawchemyTypeWithStrawberryObjectDefinition(StrawchemyDTOAttributes, WithStrawberryObjectDefinition): ...

    class StrawchemyTypeFromPydantic(StrawchemyDTOAttributes, StrawberryTypeFromPydantic[PydanticModel]): ...
