import warnings
import uuid

warnings.filterwarnings("ignore")

import os
from fastapi.testclient import TestClient
import asyncpg
import psycopg2
from http import HTTPStatus
import pytest
from unittest.mock import patch, AsyncMock
from pathlib import Path

from hse_backend.main import app
from hse_backend.repositories.moderation import ModerationRepository
from hse_backend.workers import ModerationWorker
from hse_backend.repositories.users import UserRepository
from hse_backend.repositories.ads import AdRepository
from hse_backend.repositories.prediction_cache import PredictionCacheStorage

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5435/service"
)

import pytest

pytest_plugins = ("pytest_asyncio",)


# Конфигурация для избежания конфликтов event loop
@pytest.fixture(scope="session")
def event_loop_policy():
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# очистка БД перед каждым тестом, синхронная версия работает для всех тестов, асинхроснная написана в качестве примера, но не используется, так как в тестах используется TestClient, который не поддерживает асинхронные фикстуры
# @pytest.fixture(autouse=True)
# async def clean_db():
#     conn = await asyncpg.connect(DATABASE_URL)
#     try:
#         await conn.execute("TRUNCATE TABLE ads, users RESTART IDENTITY CASCADE;")
#         yield
#     finally:
#         await conn.close()


@pytest.fixture(autouse=True)
def clean_db_sync():
    conn = psycopg2.connect(
        host="localhost",
        port=5435,
        database="service",
        user="postgres",
        password="postgres",
    )
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(
            "TRUNCATE TABLE ads, users, account, moderation_results RESTART IDENTITY CASCADE;"
        )
    finally:
        cur.close()
        conn.close()


# Тесты ручки /simple_predict
def test_simple_predict_ad_not_found(authenticated_client):
    # база данных пуста
    item_id = 12345

    with patch(
        "hse_backend.routes.predict_violation.AdRepository.get_ad_with_seller",
        new=AsyncMock(return_value=None),
    ):
        response = authenticated_client.get(f"/predict/simple_predict/{item_id}")
        assert response.status_code == HTTPStatus.NOT_FOUND
        assert "not found" in response.json()["detail"].lower()


def test_simple_predict_incorrect_item_id(authenticated_client):
    # item_id < 0
    item_id = -1

    response = authenticated_client.get(f"/predict/simple_predict/{item_id}")
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "item_id must be a positive integer" in response.json()["detail"]


def test_simple_predict_itemid_not_specified(authenticated_client):
    # item_id не указан
    response = authenticated_client.get("/predict/simple_predict/")
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_simple_predict_itemid_not_integer(authenticated_client):
    # item_id не является целым числом
    item_id = "abc"

    response = authenticated_client.get(f"/predict/simple_predict/{item_id}")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


# Тесты репозитория users
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_id,is_verified",
    [
        (1, True),
        (2, False),
    ],
)
async def test_user_repository_create_and_get(user_id: int, is_verified: bool):
    repo = UserRepository()

    # создание и получение пользователя
    await repo.create_user(user_id=user_id, is_verified=is_verified)
    user = await repo.get_user_by_id(user_id)

    assert user is not None
    assert user["id"] == user_id
    assert user["is_verified"] is is_verified


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_user_id, expected_exception, expected_message",
    [
        # некорректные целые числа
        (-1, ValueError, "user_id must be a positive integer"),
        (0, ValueError, "user_id must be a positive integer"),
        (-999, ValueError, "user_id must be a positive integer"),
        # некорректные типы
        ("", TypeError, "user_id must be an integer"),
        ("abc", TypeError, "user_id must be an integer"),
        (None, TypeError, "user_id must be an integer"),
        (1.23, TypeError, "user_id must be an integer"),
    ],
)
async def test_user_repository_create_invalid_user_id(
    invalid_user_id, expected_exception, expected_message
):
    repo = UserRepository()
    with pytest.raises(expected_exception, match=expected_message):
        await repo.create_user(user_id=invalid_user_id, is_verified=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id_not_found", [1234567890, 999999999])
async def test_user_repository_user_id_not_found(user_id_not_found):
    # несуществующий user_id

    repo = UserRepository()
    assert await repo.get_user_by_id(user_id_not_found) is None


# Тесты репозитория ads
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "seller_id, is_verified, should_succeed",
    [
        (20019, False, True),
        (999999, True, False),
    ],
)
async def test_ad_repository_create_and_get(
    seller_id: int, is_verified: bool | None, should_succeed: bool
):
    user_repo = UserRepository()
    ad_repo = AdRepository()

    item_id = 123456789

    if should_succeed:
        await user_repo.create_user(seller_id, is_verified=is_verified)

    if should_succeed:
        # попытка создать объявление с существующим seller_id должна закнчиться успешно
        ad = await ad_repo.create_ad(
            seller_id=seller_id,
            item_id=item_id,
            name="Test item",
            description="Test description",
            category=3,
            images_qty=2,
        )

        assert "item_id" in ad
        assert ad["seller_id"] == seller_id

        full_ad = await ad_repo.get_ad_with_seller(ad["item_id"])
        assert full_ad is not None
        assert full_ad["is_verified_seller"] is is_verified

    else:
        # попытка создать объявление с несуществующим seller_id должна вызвать ошибку
        with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
            await ad_repo.create_ad(
                seller_id=seller_id,
                item_id=item_id,
                name="Test",
                description="Test",
                category=1,
                images_qty=0,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_item_id, expected_exception, expected_message",
    [
        # некорректные целые числа
        (-1, ValueError, "item_id must be a positive integer"),
        (0, ValueError, "item_id must be a positive integer"),
        (-999, ValueError, "item_id must be a positive integer"),
        # некорректные типы
        ("", TypeError, "item_id must be an integer"),
        ("abc", TypeError, "item_id must be an integer"),
        (None, TypeError, "item_id must be an integer"),
        (1.23, TypeError, "item_id must be an integer"),
    ],
)
async def test_create_ad_with_invalid_item_id(
    invalid_item_id, expected_exception, expected_message
):
    user_repo = UserRepository()
    ad_repo = AdRepository()

    seller_id = 12345
    await user_repo.create_user(seller_id, is_verified=True)

    with pytest.raises(expected_exception, match=expected_message):
        await ad_repo.create_ad(
            seller_id=seller_id,
            item_id=invalid_item_id,
            name="Test",
            description="Test",
            category=1,
            images_qty=0,
        )


@pytest.mark.asyncio
async def test_duplicated_item_id():
    # при создании объявления с уже существующим item_id должна возникать ошибка

    user_repo = UserRepository()
    ad_repo = AdRepository()

    await user_repo.create_user(user_id=1, is_verified=False)

    await ad_repo.create_ad(
        seller_id=1,
        item_id=987654321,
        name="Test item 1",
        description="Test description 1",
        category=1,
        images_qty=1,
    )

    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await ad_repo.create_ad(
            seller_id=1,
            item_id=987654321,
            name="Test item 2",
            description="Test description 2",
            category=2,
            images_qty=2,
        )


# Тесты на корректность предсказаний модели
# решающее правило y = (X[:, 0] < 0.3) & (X[:, 1] < 0.2)
# Признаки: [is_verified_seller, images_qty, description_length, category]
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "seller_id, is_verified_seller, item_id, name, description, category, images_qty, expected_is_violation",
    [
        # not violation - is_verified_seller = True (1.0 >= 0.3)
        (8237, True, 5602, "название товара", "описание товара", 1, 5, False),
        (8237, True, 5603, "название товара", "описание товара", 1, 1, False),
        # not violation - is_verified_seller = False, но images_qty = 5 , 0.5 >= 0.2
        (8238, False, 5604, "название товара", "описание товара", 1, 5, False),
        # violation - is_verified_seller = False и images_qty <= 1 , (0.0 < 0.3) и (0.1 < 0.2)
        (8239, False, 5605, "название товара", "описание товара", 1, 1, True),
        (8240, False, 5606, "название товара", "описание товара", 1, 0, True),
    ],
)
async def test_simple_predict_integration(
    authenticated_client,
    seller_id: int,
    is_verified_seller: bool,
    item_id: int,
    name: str,
    description: str,
    category: int,
    images_qty: int,
    expected_is_violation: bool,
):
    user_repo = UserRepository()
    await user_repo.create_user(user_id=seller_id, is_verified=is_verified_seller)

    ad_repo = AdRepository()
    await ad_repo.create_ad(
        seller_id=seller_id,
        item_id=item_id,
        name=name,
        description=description,
        category=category,
        images_qty=images_qty,
    )

    response = authenticated_client.get(f"/predict/simple_predict/{item_id}")

    assert response.status_code == HTTPStatus.OK
    result = response.json()
    assert result["is_violation"] is expected_is_violation
    assert isinstance(result["probability"], float)
    assert 0.0 <= result["probability"] <= 1.0


# Тесты на ошибки 500, 503 для модели
@pytest.mark.asyncio
async def test_simple_predict_503_model_not_loaded(authenticated_client):
    seller_id = 999
    item_id = 888
    user_repo = UserRepository()
    ad_repo = AdRepository()

    await user_repo.create_user(seller_id, is_verified=False)
    await ad_repo.create_ad(
        seller_id=seller_id,
        item_id=item_id,
        name="test",
        description="test desc",
        category=1,
        images_qty=0,
    )

    original_model = app.state.models.pop("violation_model", None)

    try:
        response = authenticated_client.get(f"/predict/simple_predict/{item_id}")
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.json()["detail"] == "ML model is not loaded"
    finally:
        if original_model is not None:
            app.state.models["violation_model"] = original_model


@pytest.mark.asyncio
async def test_simple_predict_500_prediction_failure(authenticated_client):
    seller_id = 998
    item_id = 887
    user_repo = UserRepository()
    ad_repo = AdRepository()

    await user_repo.create_user(seller_id, is_verified=False)
    await ad_repo.create_ad(
        seller_id=seller_id,
        item_id=item_id,
        name="test",
        description="test desc",
        category=1,
        images_qty=0,
    )

    with patch(
        "hse_backend.routes.predict_violation.predict_violation",
        side_effect=RuntimeError("Mocked prediction error"),
    ):
        response = authenticated_client.get(f"/predict/simple_predict/{item_id}")
        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert "Prediction failed" in response.json()["detail"]


# Тесты ручки /async_predict
@pytest.mark.asyncio
async def test_async_predict_creates_moderation_task(authenticated_client):
    user_repo = UserRepository()
    ad_repo = AdRepository()

    seller_id = 100
    item_id = 1000
    await user_repo.create_user(seller_id, is_verified=False)
    await ad_repo.create_ad(
        seller_id=seller_id,
        item_id=item_id,
        name="Test async ad",
        description="Test description",
        category=1,
        images_qty=0,
    )

    with patch.object(
        app.state.kafka_producer, "send_moderation_request", new_callable=AsyncMock
    ):
        response = authenticated_client.post(
            "/predict/async_predict", json={"item_id": item_id}
        )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "pending"
    assert data["message"] == "Moderation request accepted"

    mod_repo = ModerationRepository()
    record = await mod_repo.get_by_id(data["task_id"])
    assert record["item_id"] == item_id
    assert record["status"] == "pending"
    assert record["is_violation"] is None


def test_async_predict_invalid_item_id(authenticated_client):
    response = authenticated_client.post("/predict/async_predict", json={"item_id": -1})
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "positive integer" in response.json()["detail"]


def test_async_predict_ad_not_found(authenticated_client):
    # объявление не создано
    response = authenticated_client.post(
        "/predict/async_predict", json={"item_id": 999999}
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert "Ad not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_moderation_result_pending(authenticated_client):
    user_repo = UserRepository()
    ad_repo = AdRepository()
    await user_repo.create_user(200, is_verified=False)
    await ad_repo.create_ad(
        seller_id=200,
        item_id=123,
        name="Pending ad",
        description="...",
        category=1,
        images_qty=0,
    )

    mod_repo = ModerationRepository()
    record = await mod_repo.create_pending(item_id=123)

    response = authenticated_client.get(f"/predict/moderation_result/{record['id']}")
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["task_id"] == record["id"]
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_get_moderation_result_completed(authenticated_client):
    user_repo = UserRepository()
    ad_repo = AdRepository()
    await user_repo.create_user(300, is_verified=False)
    await ad_repo.create_ad(
        seller_id=300,
        item_id=456,
        name="Completed ad",
        description="...",
        category=1,
        images_qty=0,
    )

    # вставляем запись в бд
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO moderation_results 
            (item_id, status, is_violation, probability, processed_at)
            VALUES ($1, $2, $3, $4, NOW())
            RETURNING id
        """,
            456,
            "completed",
            True,
            0.87,
        )
        task_id = row["id"]
    finally:
        await conn.close()

    response = authenticated_client.get(f"/predict/moderation_result/{task_id}")
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["status"] == "completed"
    assert data["is_violation"] is True
    assert data["probability"] == 0.87


def test_get_moderation_result_not_found(authenticated_client):
    response = authenticated_client.get("/predict/moderation_result/999999")
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert "Task with id = 999999 not found" in response.json()["detail"]


# Тесты kafka и воркера
@pytest.mark.asyncio
@patch("hse_backend.workers.moderation_worker.KafkaProducer")
async def test_worker_processes_message_success(mock_kafka_producer_class):
    """
    Unit test: Verify worker calls repository methods with correct parameters.
    Business logic: predict_violation is called and cache/moderation is updated.
    """
    mock_kafka_instance = AsyncMock()
    mock_kafka_producer_class.return_value = mock_kafka_instance

    ad_data = {
        "item_id": 101,
        "seller_id": 202,
        "is_verified_seller": False,
        "name": "Test",
        "description": "Desc",
        "category": 1,
        "images_qty": 0,
    }

    with patch(
        "hse_backend.workers.moderation_worker.load_model"
    ) as mock_load_model, patch(
        "hse_backend.workers.moderation_worker.predict_violation"
    ) as mock_predict, patch.object(
        AdRepository, "get_ad_with_seller", new_callable=AsyncMock
    ) as mock_get_ad, patch.object(
        ModerationRepository, "get_pending_by_item_id", new_callable=AsyncMock
    ) as mock_get_pending, patch.object(
        ModerationRepository, "update_completed", new_callable=AsyncMock
    ) as mock_update_completed, patch.object(
        PredictionCacheStorage, "set_prediction_cache", new_callable=AsyncMock
    ) as mock_cache:

        mock_load_model.return_value = "mocked_model"
        mock_predict.return_value = {"is_violation": True, "probability": 0.92}
        mock_get_ad.return_value = ad_data
        mock_get_pending.return_value = {"id": 50}

        worker = ModerationWorker(Path("../ml_models/model.pkl"))
        success = await worker.process_message_with_retry({"item_id": 101})

        assert success is True

        # Verify repository methods were called with correct parameters
        mock_get_ad.assert_called_once_with(101)
        mock_get_pending.assert_called_once_with(101)
        mock_cache.assert_called_once_with(
            101, {"is_violation": True, "probability": 0.92}
        )
        mock_update_completed.assert_called_once_with(50, True, 0.92)


@pytest.mark.asyncio
@patch("hse_backend.workers.moderation_worker.KafkaProducer")
async def test_worker_sends_to_dlq_on_error(mock_kafka_producer_class):
    """
    Unit test: Verify worker handles errors and updates status to 'failed'.
    Tests repository methods are called with correct error parameters.
    """
    mock_kafka_instance = AsyncMock()
    mock_kafka_producer_class.return_value = mock_kafka_instance

    with patch(
        "hse_backend.workers.moderation_worker.load_model"
    ) as mock_load_model, patch(
        "hse_backend.workers.moderation_worker.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep, patch.object(
        AdRepository, "get_ad_with_seller", new_callable=AsyncMock
    ) as mock_get_ad, patch.object(
        ModerationRepository, "update_failed", new_callable=AsyncMock
    ) as mock_update_failed:

        mock_load_model.return_value = "mocked_model"
        mock_get_ad.return_value = None  # Ad not found

        worker = ModerationWorker(Path("../ml_models/model.pkl"))
        await worker.start()  # Start the producer
        success = await worker.process_message_with_retry({"item_id": 999})

        assert success is False

        # Verify error was recorded in database
        mock_update_failed.assert_called_once()
        args = mock_update_failed.call_args
        item_id = args[0][0]
        error_msg = args[0][1]
        assert item_id == 999
        assert "not found" in error_msg.lower()

        # DLQ
        mock_kafka_instance.send_json.assert_called_once()
        args, _ = mock_kafka_instance.send_json.call_args
        topic, message = args
        assert topic == "moderation_dlq"
        assert message["original_message"]["item_id"] == 999
        assert "not found" in message["error"]
        assert message["retry_count"] == 3


@pytest.mark.asyncio
@patch(
    "hse_backend.workers.moderation_worker.predict_violation",
    side_effect=ConnectionError("ML service is temporarily unavailable"),
)
@patch("hse_backend.workers.moderation_worker.asyncio.sleep", new_callable=AsyncMock)
@patch("hse_backend.workers.moderation_worker.KafkaProducer")
async def test_worker_retries_on_temporary_error(
    mock_kafka_producer_class, mock_sleep, mock_predict
):
    """
    Unit test: Verify worker retries on temporary errors and eventually fails.
    Tests that update_failed is called with error message after max retries.
    """
    mock_kafka_instance = AsyncMock()
    mock_kafka_producer_class.return_value = mock_kafka_instance

    ad_data = {
        "item_id": 123,
        "seller_id": 456,
        "is_verified_seller": False,
        "name": "Test Ad",
        "description": "Test description",
        "category": 1,
        "images_qty": 0,
    }

    with patch(
        "hse_backend.workers.moderation_worker.load_model"
    ) as mock_load_model, patch.object(
        AdRepository, "get_ad_with_seller", new_callable=AsyncMock
    ) as mock_get_ad, patch.object(
        ModerationRepository, "get_pending_by_item_id", new_callable=AsyncMock
    ) as mock_get_pending, patch.object(
        ModerationRepository, "update_failed", new_callable=AsyncMock
    ) as mock_update_failed:

        mock_load_model.return_value = "mocked_model"
        mock_get_ad.return_value = ad_data
        mock_get_pending.return_value = {"id": 99}

        worker = ModerationWorker(Path("../ml_models/model.pkl"))
        await worker.start()
        success = await worker.process_message_with_retry({"item_id": 123})

        # After max retries, should fail
        assert success is False

        # Verify retry mechanism
        assert mock_predict.call_count == 3  # 3 retry attempts
        assert mock_sleep.call_count == 2  # 2 sleeps between retries

        # Verify update_failed was called with the error message
        mock_update_failed.assert_called_once()
        args = mock_update_failed.call_args
        item_id = args[0][0]
        error_msg = args[0][1]
        assert item_id == 123
        assert "ML service is temporarily unavailable" in error_msg


# Отправка нескольких запросов с одним item_id
@pytest.mark.asyncio
async def test_multiple_async_predict_same_item(authenticated_client):
    user_repo = UserRepository()
    ad_repo = AdRepository()

    seller_id = 777
    item_id = 8888
    await user_repo.create_user(seller_id, is_verified=False)
    await ad_repo.create_ad(
        seller_id=seller_id,
        item_id=item_id,
        name="Duplicate test ad",
        description="For idempotency check",
        category=2,
        images_qty=1,
    )

    with patch.object(
        app.state.kafka_producer, "send_moderation_request", new_callable=AsyncMock
    ):
        resp1 = authenticated_client.post(
            "/predict/async_predict", json={"item_id": item_id}
        )
        resp2 = authenticated_client.post(
            "/predict/async_predict", json={"item_id": item_id}
        )

    assert resp1.status_code == HTTPStatus.OK
    assert resp2.status_code == HTTPStatus.OK

    data1 = resp1.json()
    data2 = resp2.json()

    assert data1["status"] == "pending"
    assert data2["status"] == "pending"
    assert data1["task_id"] != data2["task_id"]

    mod_repo = ModerationRepository()
    record1 = await mod_repo.get_by_id(data1["task_id"])
    record2 = await mod_repo.get_by_id(data2["task_id"])

    assert record1["item_id"] == item_id
    assert record2["item_id"] == item_id
    assert record1["id"] != record2["id"]


# Тесты на закрытие объявления
@pytest.mark.integration
@pytest.mark.asyncio
async def test_close_ad_repository_success():

    # корректное обновление флага при закрытии

    user_repo = UserRepository()
    ad_repo = AdRepository()

    seller_id = 450
    item_id = 4500
    await user_repo.create_user(seller_id, is_verified=True)
    await ad_repo.create_ad(
        seller_id=seller_id,
        item_id=item_id,
        name="Ad to close",
        description="Test ad",
        category=1,
        images_qty=2,
    )

    ad = await ad_repo.get_ad_with_seller(item_id)
    assert ad is not None

    result = await ad_repo.close_ad(item_id)
    assert result is True

    ad_after = await ad_repo.get_ad_with_seller(item_id)
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow(
            "SELECT is_closed FROM ads WHERE item_id = $1", item_id
        )
        assert row is not None
        assert row["is_closed"] is True
    finally:
        await conn.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_close_ad_not_found():

    # попытка закрыть несуществующее объявление должна вернуть false

    ad_repo = AdRepository()

    result = await ad_repo.close_ad(999999)
    assert result is False


@pytest.mark.asyncio
async def test_close_ad_invalid_item_id():
    ad_repo = AdRepository()

    with pytest.raises(ValueError, match="item_id must be a positive integer"):
        await ad_repo.close_ad(-1)

    with pytest.raises(ValueError, match="item_id must be a positive integer"):
        await ad_repo.close_ad(0)

    with pytest.raises(TypeError, match="item_id must be an integer"):
        await ad_repo.close_ad("invalid")


def test_close_ad_endpoint_invalid_item_id(authenticated_client):
    response = authenticated_client.delete("/predict/close/-1")
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "positive integer" in response.json()["detail"]


def test_close_ad_endpoint_ad_not_found(authenticated_client):
    response = authenticated_client.delete("/predict/close/999999")
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert "not found" in response.json()["detail"]


@pytest.mark.integration
async def test_close_ad_endpoint_success(authenticated_client):
    user_repo = UserRepository()
    ad_repo = AdRepository()

    seller_id = 550
    item_id = 5500
    await user_repo.create_user(seller_id, is_verified=False)
    await ad_repo.create_ad(
        seller_id=seller_id,
        item_id=item_id,
        name="Ad to close via endpoint",
        description="Test description",
        category=2,
        images_qty=1,
    )

    ad_before = await ad_repo.get_ad_with_seller(item_id)
    assert ad_before is not None

    response = authenticated_client.delete(f"/predict/close/{item_id}")
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert "closed successfully" in data["message"]
    assert data["item_id"] == item_id

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow(
            "SELECT is_closed FROM ads WHERE item_id = $1", item_id
        )
        assert row is not None
        assert row["is_closed"] is True
    finally:
        await conn.close()


def test_close_ad_endpoint_deletes_cache(authenticated_client):

    # при закрытии объявления должен удаляться кэш предсказания для этого item_id

    item_id = 6600

    with patch("hse_backend.routes.predict_violation.ad_repo") as mock_ad_repo, patch(
        "hse_backend.routes.predict_violation.cache_storage"
    ) as mock_cache:

        async def mock_close_ad(*args, **kwargs):
            return True

        mock_ad_repo.close_ad = mock_close_ad
        mock_cache.delete_prediction_cache = AsyncMock(return_value=True)

        response = authenticated_client.delete(f"/predict/close/{item_id}")

        assert response.status_code == HTTPStatus.OK
        assert "closed successfully" in response.json()["message"]

        mock_cache.delete_prediction_cache.assert_called_once_with(item_id)
