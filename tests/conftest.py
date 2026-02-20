import pytest
import sys
from pathlib import Path
import pytest
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

from clients.redis import redis_client

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


@pytest.fixture(autouse=True)
def clean_redis_cache():
    # очистка кэша перед каждым тестом

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
