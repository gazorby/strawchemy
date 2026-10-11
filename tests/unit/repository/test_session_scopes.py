"""Tests for the read and write session scopes."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import String, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_scoped_session, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from strawchemy.repository.strawberry._session import (
    async_locked,
    async_read_scope,
    async_write_scope,
    has_pending_writes,
    sync_locked,
    sync_read_scope,
    sync_write_scope,
)
from strawchemy.utils.strawberry import default_session_getter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from strawberry import Info


class _Base(DeclarativeBase): ...


class Item(_Base):
    """Minimal table the scopes read and write."""

    __tablename__ = "item"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)


def _info(context: dict[str, Any]) -> Info[Any, Any]:
    return cast("Info[Any, Any]", SimpleNamespace(context=context))


class Env(SimpleNamespace):
    """Sessions and getters recording opened and closed read sessions."""

    sessionmaker: async_sessionmaker[AsyncSession]
    request_session: AsyncSession
    opened: list[AsyncSession]
    closed: list[AsyncSession]
    info: Any
    read_getter: Any


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[Env]:
    """Provide a file-backed aiosqlite environment so sessions use independent connections."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/scopes.db")
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
        await conn.execute(insert(Item).values(id=1, name="a"))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    opened: list[AsyncSession] = []
    closed: list[AsyncSession] = []

    def read_getter(_: object) -> AsyncSession:
        session = maker()
        original_close = session.close

        async def close() -> None:
            closed.append(session)
            await original_close()

        session.close = close  # ty: ignore[invalid-assignment]  # record closures
        opened.append(session)
        return session

    request_session = maker()
    yield Env(
        sessionmaker=maker,
        request_session=request_session,
        opened=opened,
        closed=closed,
        info=_info({"session": request_session}),
        read_getter=read_getter,
    )
    await request_session.close()
    await engine.dispose()


async def test_read_scope_uses_read_session(env: Env) -> None:
    """Test that a read scope yields a fresh session when the request session has no pending writes."""
    async with async_read_scope(env.info, default_session_getter, env.read_getter) as session:
        assert session is not env.request_session
    assert env.opened == [session]
    assert env.closed == [session]


async def test_read_scope_without_getter_uses_request_session(env: Env) -> None:
    """Test that a read scope yields the request session when no read getter is configured."""
    async with async_read_scope(env.info, default_session_getter, None) as session:
        assert session is env.request_session
    assert env.opened == []


async def test_read_scope_falls_back_after_write_scope(env: Env) -> None:
    """Test that a read scope yields the request session once a write scope ran in its transaction."""
    async with async_write_scope(env.info, default_session_getter) as session:
        await session.execute(update(Item).values(name="x"))
    async with async_read_scope(env.info, default_session_getter, env.read_getter) as session:
        assert session is env.request_session
    assert env.opened == []


@pytest.mark.parametrize("end", ["commit", "rollback"])
async def test_pending_writes_cleared_by_transaction_end(end: str, env: Env) -> None:
    """Test that committing or rolling back the request session clears its pending writes."""
    async with async_write_scope(env.info, default_session_getter) as session:
        await session.execute(update(Item).values(name="x"))
    assert has_pending_writes(env.request_session)
    await getattr(env.request_session, end)()
    assert not has_pending_writes(env.request_session)


async def test_pending_writes_on_unflushed_add(env: Env) -> None:
    """Test that an unflushed add counts as a pending write."""
    env.request_session.add(Item(id=2, name="y"))
    assert has_pending_writes(env.request_session)


async def test_write_scope_records_on_error(env: Env) -> None:
    """Test that a write scope that raises still records the write."""

    async def failing_write() -> None:
        async with async_write_scope(env.info, default_session_getter) as session:
            await session.execute(update(Item).values(name="x"))
            raise RuntimeError

    with pytest.raises(RuntimeError):
        await failing_write()
    assert has_pending_writes(env.request_session)


async def test_read_session_closed_on_error(env: Env) -> None:
    """Test that a read session is closed when the body raises."""
    with pytest.raises(RuntimeError):
        async with async_read_scope(env.info, default_session_getter, env.read_getter):
            raise RuntimeError
    assert len(env.opened) == 1
    assert env.closed == env.opened


async def test_read_scope_without_request_session(env: Env) -> None:
    """Test that a read scope uses a read session when the context carries no request session."""
    info = _info({})
    async with async_read_scope(info, default_session_getter, env.read_getter) as session:
        assert session is not env.request_session
    assert env.closed == [session]


async def test_scoped_session_pending_writes(env: Env) -> None:
    """Test that pending writes are tracked through an async_scoped_session."""
    scoped = async_scoped_session(env.sessionmaker, scopefunc=lambda: 1)
    info = _info({"session": scoped})
    try:
        assert not has_pending_writes(scoped)
        async with async_write_scope(info, default_session_getter) as session:
            await session.execute(update(Item).values(name="x"))
        assert has_pending_writes(scoped)
    finally:
        await scoped.remove()


def test_sync_read_scope_yields_request_session() -> None:
    """Test that the sync read scope yields the request session even with a read getter."""
    request_session = sessionmaker()()
    info = _info({"session": request_session})

    def read_getter(_: object) -> Session:
        raise AssertionError

    with sync_read_scope(info, default_session_getter, read_getter) as session:
        assert session is request_session


async def test_write_scope_nests_in_same_task(env: Env) -> None:
    """Test that a scope on a session already locked by the same task does not wait on itself."""

    async def nested() -> None:
        async with async_write_scope(env.info, default_session_getter) as session, async_locked(session):
            await session.execute(select(Item))

    await asyncio.wait_for(nested(), timeout=5)


async def test_lock_still_serializes_tasks(env: Env) -> None:
    """Test that another task waits for the lock held by a scope."""
    events: list[str] = []

    async def other() -> None:
        async with async_locked(env.request_session):
            events.append("other")

    async with async_locked(env.request_session):
        task = asyncio.create_task(other())
        await asyncio.sleep(0.01)
        events.append("owner")
    await asyncio.wait_for(task, timeout=5)
    assert events == ["owner", "other"]


def test_sync_write_scope_nests() -> None:
    """Test that a sync scope nested in another on the same session does not deadlock."""
    info = _info({"session": sessionmaker()()})

    def nested() -> None:
        with sync_write_scope(info, default_session_getter) as session, sync_locked(session):
            pass

    thread = threading.Thread(target=nested, daemon=True)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()


async def test_fallback_read_keeps_flushed_add_visible(env: Env) -> None:
    """Test that a read flushing pending adds on the request session keeps later reads on it."""
    env.request_session.add(Item(id=2, name="y"))
    async with async_read_scope(env.info, default_session_getter, env.read_getter) as session:
        assert session is env.request_session
        await session.execute(select(Item))
    assert not env.request_session.new
    async with async_read_scope(env.info, default_session_getter, env.read_getter) as session:
        assert session is env.request_session
    assert env.opened == []
