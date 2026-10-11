from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession, async_scoped_session
from sqlalchemy.orm import Session, scoped_session

from strawchemy.exceptions import SessionNotFoundError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from contextlib import AbstractAsyncContextManager, AbstractContextManager
    from types import TracebackType

    from strawberry import Info

    from strawchemy.repository.typing import (
        AnyAsyncSession,
        AnySession,
        AnySyncSession,
        AsyncSessionGetter,
        SyncSessionGetter,
    )

__all__ = (
    "SessionScope",
    "async_locked",
    "async_locked_write",
    "async_read_scope",
    "async_write_scope",
    "has_pending_writes",
    "sync_locked",
    "sync_locked_write",
    "sync_read_scope",
    "sync_write_scope",
)

_SESSION_LOCK_KEY = "strawchemy_session_lock"
_WRITE_TXN_KEY = "strawchemy_write_txn"


@dataclass(slots=True)
class _TaskLock:
    """Lock the task holding it can acquire again, so session scopes nest within one resolver."""

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _owner: asyncio.Task[Any] | None = None
    _depth: int = 0

    async def __aenter__(self) -> None:
        task = asyncio.current_task()
        if task is None or self._owner is not task:
            await self._lock.acquire()
            self._owner = task
        self._depth += 1

    async def __aexit__(self, *_: object) -> None:
        self._depth -= 1
        if self._depth == 0:
            self._owner = None
            self._lock.release()


def _underlying_session(session: AnySession) -> Session:
    if isinstance(session, (async_scoped_session, scoped_session)):
        session = session()
    return session.sync_session if isinstance(session, AsyncSession) else session


def _record_write(session: AnySession) -> None:
    session.info[_WRITE_TXN_KEY] = _underlying_session(session).get_transaction()


def has_pending_writes(session: AnySession) -> bool:
    """Return whether the session holds writes that another session could not see."""
    sync_session = _underlying_session(session)
    if sync_session.new or sync_session.dirty or sync_session.deleted:
        return True
    written_in = session.info.get(_WRITE_TXN_KEY)
    return written_in is not None and written_in is sync_session.get_transaction() and written_in.is_active


@asynccontextmanager
async def async_locked(session: AnyAsyncSession) -> AsyncIterator[AnyAsyncSession]:
    """Yield the session while holding its lock, as a session forbids concurrent operations."""
    async with session.info.setdefault(_SESSION_LOCK_KEY, _TaskLock()):
        yield session


@contextmanager
def sync_locked(session: AnySyncSession) -> Iterator[AnySyncSession]:
    """Yield the session while holding its lock."""
    with session.info.setdefault(_SESSION_LOCK_KEY, threading.RLock()):
        yield session


@asynccontextmanager
async def async_locked_write(session: AnyAsyncSession) -> AsyncIterator[AnyAsyncSession]:
    """Yield the session under its lock and record that it was written to."""
    try:
        async with async_locked(session) as locked:
            yield locked
    finally:
        _record_write(session)


@contextmanager
def sync_locked_write(session: AnySyncSession) -> Iterator[AnySyncSession]:
    """Yield the session under its lock and record that it was written to."""
    try:
        with sync_locked(session) as locked:
            yield locked
    finally:
        _record_write(session)


@asynccontextmanager
async def async_read_scope(
    info: Info[Any, Any], session_getter: AsyncSessionGetter, read_session_getter: AsyncSessionGetter | None
) -> AsyncIterator[AnyAsyncSession]:
    """Yield a session to read from: a dedicated one unless the request session has pending writes."""
    request_session: AnyAsyncSession | None = None
    try:
        request_session = session_getter(info)
    except SessionNotFoundError:
        if read_session_getter is None:
            raise
    if request_session is None or (read_session_getter is not None and not has_pending_writes(request_session)):
        assert read_session_getter is not None
        read_session = read_session_getter(info)
        try:
            yield read_session
        finally:
            await read_session.close()
    else:
        async with async_locked_write(request_session) as session:  # autoflush empties `new` without a marker
            yield session


@asynccontextmanager
async def async_write_scope(info: Info[Any, Any], session_getter: AsyncSessionGetter) -> AsyncIterator[AnyAsyncSession]:
    """Yield the request session under its lock and record that it was written to."""
    async with async_locked_write(session_getter(info)) as session:
        yield session


@contextmanager
def sync_read_scope(
    info: Info[Any, Any],
    session_getter: SyncSessionGetter,
    read_session_getter: SyncSessionGetter | None,  # noqa: ARG001
) -> Iterator[AnySyncSession]:
    """Yield the request session under its lock, as sync reads are never concurrent."""
    with sync_locked(session_getter(info)) as session:
        yield session


@contextmanager
def sync_write_scope(info: Info[Any, Any], session_getter: SyncSessionGetter) -> Iterator[AnySyncSession]:
    """Yield the request session under its lock and record that it was written to."""
    with sync_locked_write(session_getter(info)) as session:
        yield session


class SessionScope:
    """Session scope usable with ``async with`` or ``with``, delegating to the matching async or sync scope."""

    def __init__(
        self,
        async_scope: AbstractAsyncContextManager[AnyAsyncSession],
        sync_scope: AbstractContextManager[AnySyncSession],
    ) -> None:
        self._async_scope = async_scope
        self._sync_scope = sync_scope

    async def __aenter__(self) -> AnyAsyncSession:
        return await self._async_scope.__aenter__()

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> bool | None:
        return await self._async_scope.__aexit__(exc_type, exc, tb)

    def __enter__(self) -> AnySyncSession:
        return self._sync_scope.__enter__()

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> bool | None:
        return self._sync_scope.__exit__(exc_type, exc, tb)
