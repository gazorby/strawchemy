from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
    from strawchemy.graphql.mutation import Input

SQLAlchemyInput: TypeAlias = "Input[DeclarativeBase, QueryableAttribute[Any], Any]"
