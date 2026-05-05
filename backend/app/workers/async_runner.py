from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import Future as ThreadFuture
from threading import Thread
from typing import TypeVar

T = TypeVar("T")


class _AsyncLoopRunner:
    """Single background event loop for sync Celery tasks."""

    def __init__(self) -> None:
        self._ready: ThreadFuture[asyncio.AbstractEventLoop] = ThreadFuture()
        self._thread = Thread(target=self._bootstrap, name="celery-async-loop", daemon=True)
        self._thread.start()
        self._loop = self._ready.result()

    def _bootstrap(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._ready.set_result(loop)
        loop.run_forever()

    def run(self, coro: Coroutine[object, object, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()


_RUNNER: _AsyncLoopRunner | None = None


def run_async(coro: Coroutine[object, object, T]) -> T:
    """
    Celery tasks are synchronous, while DB/services are async.

    Use one dedicated background event loop per process, so async drivers (e.g. asyncpg pool)
    stay bound to a stable loop and don't fail with "Future attached to a different loop".
    """
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = _AsyncLoopRunner()
    return _RUNNER.run(coro)
