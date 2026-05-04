from __future__ import annotations

import os


def pytest_configure(config) -> None:  # type: ignore[no-untyped-def]
    # Integration tests exercise the Celery enqueue path; eager mode keeps tests hermetic.
    os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
