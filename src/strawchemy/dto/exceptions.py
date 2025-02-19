from __future__ import annotations

__all__ = ("DTOError", "EmptyDTOError", "ModelInspectorError")


class DTOError(Exception): ...


class EmptyDTOError(DTOError): ...


class ModelInspectorError(DTOError): ...
