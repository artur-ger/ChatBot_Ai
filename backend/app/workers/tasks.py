from __future__ import annotations

# Celery autodiscovery imports modules named `tasks` inside configured packages.
from app.workers import tasks_indexing  # noqa: F401
