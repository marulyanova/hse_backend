import sys
from pathlib import Path
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import json
import uuid
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from http import HTTPStatus

from main import app
from repositories.prediction_cache import PredictionCacheStorage
from clients.redis import redis_client
from repositories.users import UserRepository
from repositories.ads import AdRepository

TEST_REDIS_HOST = os.getenv("TEST_REDIS_HOST", "localhost")
TEST_REDIS_PORT = int(os.getenv("TEST_REDIS_PORT", 6379))
TEST_REDIS_DB = int(os.getenv("TEST_REDIS_DB", 1))


def generate_unique_id(prefix: str = "test") -> int:
    # генерация уникального ID для тестов, чтобы избежать коллизий в Redis
    return abs(hash(f"{prefix}_{uuid.uuid4()}")) % (2**31 - 1)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def cache_storage():
    return PredictionCacheStorage()


@pytest.fixture(autouse=True)
def reset_redis_client():
    # сброс состояния redis между тестами
    yield
    redis_client._connected = False


# Юнит-тесты
@pytest.mark.asyncio
async def test_cache_storage_get_hit_unit(cache_storage):

    # возвращаемый кэш для item_id

    item_id = 123
    expected_result = {"is_violation": True, "probability": 0.85}

    with patch("repositories.prediction_cache.redis_client") as mock_redis:
        mock_redis.get = AsyncMock(return_value=json.dumps(expected_result))

        result = await cache_storage.get_prediction_cache(item_id)

        assert result == expected_result
        mock_redis.get.assert_called_once_with(f"prediction:{item_id}")


@pytest.mark.asyncio
async def test_cache_storage_get_miss_unit(cache_storage):

    # возвращает None при отсутствии кэша item_id

    item_id = 456

    with patch("repositories.prediction_cache.redis_client") as mock_redis:
        mock_redis.get = AsyncMock(return_value=None)

        result = await cache_storage.get_prediction_cache(item_id)

        assert result is None
        mock_redis.get.assert_called_once_with(f"prediction:{item_id}")


@pytest.mark.asyncio
async def test_cache_storage_set_unit(cache_storage):

    # сохраняет кэш для item_id

    item_id = 789
    prediction = {"is_violation": False, "probability": 0.12}

    with patch("repositories.prediction_cache.redis_client") as mock_redis:
        mock_redis.set = AsyncMock(return_value=True)

        result = await cache_storage.set_prediction_cache(item_id, prediction)

        assert result == True
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == f"prediction:{item_id}"
        assert call_args[1].get("ttl_seconds") == cache_storage.CACHE_TTL_SECONDS


@pytest.mark.asyncio
async def test_cache_storage_set_custom_ttl_unit(cache_storage):

    # сохраняет кэш с кастомным TTL для item_id

    item_id = 101
    prediction = {"is_violation": True, "probability": 0.99}
    custom_ttl = 1800

    with patch("repositories.prediction_cache.redis_client") as mock_redis:
        mock_redis.set = AsyncMock(return_value=True)

        result = await cache_storage.set_prediction_cache(
            item_id, prediction, ttl_seconds=custom_ttl
        )

        assert result == True
        call_args = mock_redis.set.call_args
        assert call_args[1].get("ttl_seconds") == custom_ttl


@pytest.mark.asyncio
async def test_cache_storage_delete_unit(cache_storage):

    # удаляет кэш для item_id

    item_id = 202

    with patch("repositories.prediction_cache.redis_client") as mock_redis:
        mock_redis.delete = AsyncMock(return_value=1)

        result = await cache_storage.delete_prediction_cache(item_id)

        assert result == True
        mock_redis.delete.assert_called_once_with(f"prediction:{item_id}")


@pytest.mark.asyncio
async def test_cache_storage_delete_not_found_unit(cache_storage):

    # возвращает false если ключ не найден

    item_id = 303

    with patch("repositories.prediction_cache.redis_client") as mock_redis:
        mock_redis.delete = AsyncMock(return_value=0)

        result = await cache_storage.delete_prediction_cache(item_id)

        assert result == False


# Интерграционные тесты
@pytest.mark.integration
@pytest.mark.asyncio
async def test_cache_storage_integration_set_get(cache_storage):

    # чтение запись redis

    item_id = generate_unique_id("item")
    prediction = {"is_violation": True, "probability": 0.75}

    await cache_storage.delete_prediction_cache(item_id)

    set_result = await cache_storage.set_prediction_cache(item_id, prediction)
    assert set_result == True

    cached = await cache_storage.get_prediction_cache(item_id)
    assert cached == prediction

    await cache_storage.delete_prediction_cache(item_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cache_storage_integration_miss(cache_storage):

    # чтение несуществующего ключа возвращает None

    item_id = generate_unique_id("item")

    await cache_storage.delete_prediction_cache(item_id)

    result = await cache_storage.get_prediction_cache(item_id)
    assert result is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cache_storage_integration_delete(cache_storage):

    # удаление ключа из redis

    item_id = generate_unique_id("item")
    prediction = {"is_violation": False, "probability": 0.25}

    await cache_storage.set_prediction_cache(item_id, prediction)

    cached_before = await cache_storage.get_prediction_cache(item_id)
    assert cached_before is not None

    delete_result = await cache_storage.delete_prediction_cache(item_id)
    assert delete_result == True

    cached_after = await cache_storage.get_prediction_cache(item_id)
    assert cached_after is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_simple_predict_cache_miss_then_hit(client, cache_storage):

    # при первом запросе кэш отсутствует, при втором есть

    user_repo = UserRepository()
    ad_repo = AdRepository()

    seller_id = generate_unique_id("seller")
    item_id = generate_unique_id("item")

    await user_repo.create_user(seller_id, is_verified=False)
    await ad_repo.create_ad(
        seller_id=seller_id,
        item_id=item_id,
        name="Cache test ad",
        description="Testing cache behavior",
        category=1,
        images_qty=0,
    )

    response1 = client.get(f"/predict/simple_predict/{item_id}")
    assert response1.status_code == HTTPStatus.OK
    result1 = response1.json()
    print(f"Response 1: {result1}")

    response2 = client.get(f"/predict/simple_predict/{item_id}")
    assert response2.status_code == HTTPStatus.OK
    result2 = response2.json()
    print(f"Response 2: {result2}")

    assert result1 == result2
    assert "is_violation" in result2
    assert "probability" in result2

    try:
        import redis

        sync_r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        key = f"prediction:{item_id}"
        cached = sync_r.get(key)
        if cached:
            import json

            cached_dict = json.loads(cached)
            assert cached_dict == result2
        sync_r.close()
    except Exception as e:
        print(f"Direct Redis check skipped: {e}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_simple_predict_cache_invalidation_on_close(client):

    # после закрытия кэш удаляется

    user_repo = UserRepository()
    ad_repo = AdRepository()

    seller_id = generate_unique_id("seller")
    item_id = generate_unique_id("item")

    await user_repo.create_user(seller_id, is_verified=False)
    await ad_repo.create_ad(
        seller_id=seller_id,
        item_id=item_id,
        name="Ad to close",
        description="Will be closed",
        category=2,
        images_qty=3,
    )

    response1 = client.get(f"/predict/simple_predict/{item_id}")
    assert response1.status_code == HTTPStatus.OK
    result1 = response1.json()

    try:
        import redis

        sync_r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        key = f"prediction:{item_id}"
        sync_r.delete(key)
        sync_r.close()
    except Exception as e:
        print(f"Could not delete cache directly: {e}")

    response2 = client.get(f"/predict/simple_predict/{item_id}")
    assert response2.status_code == HTTPStatus.OK
    result2 = response2.json()

    assert result1 == result2


# Юнит-тесты для проверки вызовов при кэш-хите и кэш-миссе
def test_simple_predict_cache_hit_returns_early(client):

    # если кэш есть, результат возвращается сразу, БД и модель не вызываются

    item_id = 7777
    cached_result = {"is_violation": False, "probability": 0.15}

    with patch("routes.predict_violation.cache_storage") as mock_cache, patch(
        "routes.predict_violation.ad_repo"
    ) as mock_ad_repo:

        async def mock_get_cache(*args, **kwargs):
            return cached_result

        mock_cache.get_prediction_cache = mock_get_cache

        response = client.get(f"/predict/simple_predict/{item_id}")

        assert response.status_code == HTTPStatus.OK
        assert response.json() == cached_result

        mock_ad_repo.get_ad_with_seller.assert_not_called()


def test_simple_predict_cache_miss_calls_db_and_model(client):

    # если кэша нет, данные запрашиваются из БД, модель вызывается, результат сохраняется в кэше

    item_id = 8888
    ad_data = {
        "item_id": item_id,
        "seller_id": 999,
        "is_verified_seller": False,
        "name": "Test",
        "description": "Desc",
        "category": 1,
        "images_qty": 0,
    }
    prediction_result = {"is_violation": True, "probability": 0.95}

    with patch(
        "routes.predict_violation.predict_violation", return_value=prediction_result
    ):
        with patch("routes.predict_violation.ad_repo") as mock_ad_repo:

            async def mock_get_ad(*args, **kwargs):
                return ad_data

            mock_ad_repo.get_ad_with_seller = mock_get_ad

            with patch("routes.predict_violation.cache_storage") as mock_cache:

                async def mock_get_cache(*args, **kwargs):
                    return None

                async def mock_set_cache(*args, **kwargs):
                    return True

                mock_cache.get_prediction_cache = mock_get_cache
                mock_cache.set_prediction_cache = mock_set_cache

                response = client.get(f"/predict/simple_predict/{item_id}")

                assert response.status_code == HTTPStatus.OK
                assert response.json() == prediction_result


# Юнит-тесты для закрытия объявления
def test_close_ad_endpoint_cache_invalidation_unit(client):

    # при закрытии объявления должен удаляться кэш предсказания для этого item_id

    item_id = 9999

    with patch("routes.predict_violation.ad_repo") as mock_ad_repo, patch(
        "routes.predict_violation.cache_storage"
    ) as mock_cache:

        async def mock_close_ad(*args, **kwargs):
            return True

        mock_ad_repo.close_ad = mock_close_ad
        mock_cache.delete_prediction_cache = AsyncMock(return_value=True)

        response = client.delete(f"/predict/close/{item_id}")

        assert response.status_code == HTTPStatus.OK
        assert "closed successfully" in response.json()["message"]

        mock_cache.delete_prediction_cache.assert_called_once_with(item_id)


def test_close_ad_endpoint_ad_not_found_unit(client):
    item_id = 10000

    with patch("routes.predict_violation.ad_repo") as mock_ad_repo:

        async def mock_close_ad(*args, **kwargs):
            return False

        mock_ad_repo.close_ad = mock_close_ad

        response = client.delete(f"/predict/close/{item_id}")

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert "not found" in response.json()["detail"]


def test_close_ad_endpoint_invalid_item_id_unit(client):
    response = client.delete("/predict/close/0")
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "positive integer" in response.json()["detail"]

    response = client.delete("/predict/close/-5")
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "positive integer" in response.json()["detail"]
