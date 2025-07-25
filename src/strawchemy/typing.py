from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, Union

from typing_extensions import TypeAlias

if sys.version_info >= (3, 10):
    from types import UnionType

    UNION_TYPES = (Union, UnionType)
else:
    UNION_TYPES = (Union,)


if TYPE_CHECKING:
    from . import StrawchemyAsyncRepository, StrawchemySyncRepository

__all__ = ("UNION_TYPES", "AnyRepository", "DataclassProtocol", "SupportedDialect")


class DataclassProtocol(Protocol):
    __dataclass_fields__: ClassVar[dict[str, Any]]


AnyRepository: TypeAlias = "type[StrawchemySyncRepository[Any] | StrawchemyAsyncRepository[Any]]"
SupportedDialect: TypeAlias = Literal["postgresql", "mysql", "sqlite"]
"""Must match SQLAlchemy dialect."""
