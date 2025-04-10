from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, TypeAlias

if TYPE_CHECKING:
    from . import StrawchemyAsyncRepository, StrawchemySyncRepository

__all__ = ("AnyRepository", "DataclassProtocol", "SupportedDialect")


class DataclassProtocol(Protocol):
    __dataclass_fields__: ClassVar[dict[str, Any]]


AnyRepository: TypeAlias = "type[StrawchemySyncRepository[Any] | StrawchemyAsyncRepository[Any]]"
SupportedDialect: TypeAlias = Literal["postgresql"]
"""Must match SQLAlchemy dialect."""
