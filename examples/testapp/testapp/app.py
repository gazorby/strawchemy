from __future__ import annotations

from typing import TYPE_CHECKING

from litestar import Litestar
from litestar.plugins.sqlalchemy import EngineConfig, SQLAlchemyAsyncConfig, SQLAlchemyPlugin

from strawberry.litestar import BaseContext, make_graphql_controller

from .models import Base
from .schema import schema

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///basic_async.sqlite",
    create_all=True,
    metadata=Base.metadata,
    engine_config=EngineConfig(echo=True),
)


class GraphQLContext(BaseContext):
    session: AsyncSession


async def context_getter(db_session: AsyncSession) -> GraphQLContext:
    return GraphQLContext(db_session)


def create_app() -> Litestar:
    return Litestar(
        plugins=[SQLAlchemyPlugin(config=config)],
        route_handlers=[make_graphql_controller(schema, context_getter=context_getter)],
    )
