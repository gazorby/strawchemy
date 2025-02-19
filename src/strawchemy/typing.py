from __future__ import annotations

from typing import Any, ClassVar, Protocol


class DataclassProtocol(Protocol):
    __dataclass_fields__: ClassVar[dict[str, Any]]
