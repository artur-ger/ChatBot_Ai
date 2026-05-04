from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import Future
from threading import Thread
from typing import TypeVar

T = TypeVar("T")


def run_async(coro: Coroutine[object, object, T]) -> T:
    """
    Celery tasks are synchronous, but our DB layer is async.

    When Celery runs eagerly inside an ASGI request, there is already a running event loop in the
    current thread, so we execute the coroutine in a dedicated thread with its own loop via
    `asyncio.run`.
    """

    result: Future[T] = Future()

    def _runner() -> None:
        try:
            result.set_result(asyncio.run(coro))
        except BaseException as exc:  # noqa: BLE001
            result.set_exception(exc)

    thread = Thread(target=_runner, name="async-celery-runner", daemon=True)
    thread.start()
    thread.join()
    return result.result()
