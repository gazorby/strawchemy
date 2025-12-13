from __future__ import annotations

from types import UnionType
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, TypeAlias, Union

UNION_TYPES = (Union, UnionType)


if TYPE_CHECKING:
    from . import StrawchemyAsyncRepository, StrawchemySyncRepository

__all__ = ("UNION_TYPES", "AnyRepository", "DataclassProtocol", "SupportedDialect")


class DataclassProtocol(Protocol):
    __dataclass_fields__: ClassVar[dict[str, Any]]


AnyRepository: TypeAlias = "type[StrawchemySyncRepository[Any] | StrawchemyAsyncRepository[Any]]"
SupportedDialect: TypeAlias = Literal["postgresql", "mysql", "sqlite"]
"""Must match SQLAlchemy dialect."""
