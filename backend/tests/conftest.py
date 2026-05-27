from collections.abc import AsyncGenerator, Generator

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
os.environ.setdefault("CHROMA_HOST", "")
os.environ.setdefault("USE_FAKE_EMBEDDINGS", "true")
os.environ.setdefault("CHAT_ACL_SECRET", "test-chat-secret")
os.environ.setdefault("CHAT_ACL_DISABLED", "true")
os.environ.setdefault("ADMIN_API_AUTH_DISABLED", "true")
os.environ.setdefault("LLM_BOOTSTRAP_DEFAULT", "false")
_CHROMA_TEST_DIR = Path(tempfile.mkdtemp(prefix="chroma_tests_"))
os.environ["CHROMA_PERSIST_PATH"] = str(_CHROMA_TEST_DIR)

_DB_FILE = Path(tempfile.mkdtemp(prefix="sql_tests_")) / "app.sqlite3"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}"

from cryptography.fernet import Fernet  # noqa: E402

os.environ.setdefault("LLM_SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())

from app.db import metadata as app_metadata  # noqa: E402
from app.db.session import get_db_session  # noqa: E402

_APP = None


def get_app():
    global _APP
    if _APP is None:
        from app.main import app as fastapi_app

        _APP = fastapi_app
    return _APP


@pytest.fixture()
async def test_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(app_metadata.Base.metadata.drop_all)
        await conn.run_sync(app_metadata.Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture()
def client(test_session: AsyncSession) -> Generator[TestClient, None, None]:
    async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield test_session

    fastapi_app = get_app()
    fastapi_app.dependency_overrides[get_db_session] = _override_get_db_session
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


def pytest_sessionfinish(session, exitstatus) -> None:  # type: ignore[no-untyped-def]
    shutil.rmtree(_CHROMA_TEST_DIR, ignore_errors=True)
    shutil.rmtree(_DB_FILE.parent, ignore_errors=True)
