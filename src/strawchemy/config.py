from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .sqlalchemy import SQLAlchemyGraphQLInspector
from .strawberry import default_session_getter
from .strawberry.repository import StrawchemyAsyncRepository, StrawchemySyncRepository

if TYPE_CHECKING:
    from typing import Any

    from .graphql.inspector import GraphQLInspectorProtocol
    from .sqlalchemy.typing import FilterMap
    from .strawberry.typing import AsyncSessionGetter


@dataclass
class StrawchemyConfig:
    session_getter: AsyncSessionGetter = default_session_getter
    auto_snake_case: bool = True
    repository_type: type[StrawchemyAsyncRepository[Any] | StrawchemySyncRepository[Any]] = StrawchemyAsyncRepository
    filter_overrides: FilterMap | None = None
    execution_options: dict[str, Any] | None = None
    pagination_default_limit: int = 100
    default_id_field_name: str = "id"

    inspector: GraphQLInspectorProtocol[Any, Any] = field(init=False)

    def __post_init__(self) -> None:
        self.inspector = SQLAlchemyGraphQLInspector(filter_overrides=self.filter_overrides)
