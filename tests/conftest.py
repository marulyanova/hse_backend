import sys
import pytest
from pathlib import Path
import asyncio

# when running pytest from projects folder, ensure we can import the hse_backend package
# conftest is in hse_backend/tests, so parents[2] points to the repository root, where hse_backend folder is present
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hse_backend.clients.redis import redis_client
from hse_backend.clients.postgres import init_pool, close_pool

import pytest_asyncio


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def postgres_pool():
    await init_pool()
    yield
    await close_pool()


INVALID_PAYLOADS = [
    # нет images_qty
    {
        "seller_id": 123,
        "is_verified_seller": True,
        "item_id": 456,
        "name": "товар",
        "description": "описание",
        "category": 1,
    },
    # неправильные типы seller_id, is_verified_seller, item_id
    {
        "seller_id": "first",
        "is_verified_seller": 1.0,
        "item_id": "first",
        "name": "товар",
        "description": "описание",
        "category": 1,
        "images_qty": 3,
    },
    # пустой объект
    {},
]


@pytest.fixture
def invalid_payloads():
    return INVALID_PAYLOADS


@pytest.fixture(scope="session", autouse=True)
def setup_redis_connection():
    """
    CAUTION: session-scoped autouse fixture.
    Only use for critical setup like database/service connections.
    Individual tests should request specific fixtures if they need cleanup.
    """

    async def _connect():
        await redis_client.connect()

    asyncio.run(_connect())
    yield

    async def _close():
        if redis_client._client:
            await redis_client._client.aclose()
            redis_client._connected = False

    try:
        asyncio.run(_close())
    except RuntimeError:
        pass


@pytest.fixture()  # Removed autouse=True to prevent unwanted side effects
def clean_redis_cache():
    """
    Fixture to clean Redis cache. Use explicitly in tests that need it:

    @pytest.mark.asyncio
    async def test_something(clean_redis_cache):
        # cache is cleaned before this test
    """

    async def _clean():
        try:
            if redis_client._client:
                keys = await redis_client._client.keys("prediction:*")
                if keys:
                    await redis_client._client.delete(*keys)
        except Exception:
            pass

    asyncio.run(_clean())
    yield
