import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from fastapi.testclient import TestClient
import asyncpg
import psycopg2
from http import HTTPStatus
import pytest
from unittest.mock import patch, AsyncMock

from main import app
from repositories.moderation import ModerationRepository
from workers.moderation_worker import ModerationWorker
from repositories.users import UserRepository
from repositories.ads import AdRepository

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/service"
)


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
        port=5432,
        database="service",
        user="postgres",
        password="postgres",
    )
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute("TRUNCATE TABLE ads, users RESTART IDENTITY CASCADE;")
    finally:
        cur.close()
        conn.close()


# Тесты ручки /simple_predict
def test_simple_predict_ad_not_found(client):
    # база данных пуста
    item_id = 12345

    with patch(
        "routes.predict_violation.AdRepository.get_ad_with_seller",
        new=AsyncMock(return_value=None),
    ):
        response = client.get(f"/predict/simple_predict/{item_id}")
        assert response.status_code == HTTPStatus.NOT_FOUND
        assert "not found" in response.json()["detail"].lower()


def test_simple_predict_incorrect_item_id(client):
    # item_id < 0
    item_id = -1

    response = client.get(f"/predict/simple_predict/{item_id}")
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "item_id must be a positive integer" in response.json()["detail"]


def test_simple_predict_itemid_not_specified(client):
    # item_id не указан
    response = client.get("/predict/simple_predict/")
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_simple_predict_itemid_not_integer(client):
    # item_id не является целым числом
    item_id = "abc"

    response = client.get(f"/predict/simple_predict/{item_id}")
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

    item_id = seller_id * 1000

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
        item_id=1000,
        name="Test item 1",
        description="Test description 1",
        category=1,
        images_qty=1,
    )

    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await ad_repo.create_ad(
            seller_id=1,
            item_id=1000,
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
    client,
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

    response = client.get(f"/predict/simple_predict/{item_id}")

    assert response.status_code == HTTPStatus.OK
    result = response.json()
    assert result["is_violation"] is expected_is_violation
    assert isinstance(result["probability"], float)
    assert 0.0 <= result["probability"] <= 1.0


# Тесты на ошибки 500, 503 для модели
@pytest.mark.asyncio
async def test_simple_predict_503_model_not_loaded(client):
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
        response = client.get(f"/predict/simple_predict/{item_id}")
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.json()["detail"] == "ML model is not loaded"
    finally:
        if original_model is not None:
            app.state.models["violation_model"] = original_model


@pytest.mark.asyncio
async def test_simple_predict_500_prediction_failure(client):
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
        "routes.predict_violation.predict_violation",
        side_effect=RuntimeError("Mocked prediction error"),
    ):
        response = client.get(f"/predict/simple_predict/{item_id}")
        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert "Prediction failed" in response.json()["detail"]


# Тесты ручки /async_predict
@pytest.mark.asyncio
async def test_async_predict_creates_moderation_task(client):
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

    response = client.post("/predict/async_predict", json={"item_id": item_id})

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


def test_async_predict_invalid_item_id(client):
    response = client.post("/predict/async_predict", json={"item_id": -1})
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "positive integer" in response.json()["detail"]


def test_async_predict_ad_not_found(client):
    # объявление не создано
    response = client.post("/predict/async_predict", json={"item_id": 999999})
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert "Ad not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_moderation_result_pending(client):
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

    response = client.get(f"/predict/moderation_result/{record['id']}")
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["task_id"] == record["id"]
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_get_moderation_result_completed(client):
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

    response = client.get(f"/predict/moderation_result/{task_id}")
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["status"] == "completed"
    assert data["is_violation"] is True
    assert data["probability"] == 0.87


def test_get_moderation_result_not_found(client):
    response = client.get("/predict/moderation_result/999999")
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert "Task with id = 999999 not found" in response.json()["detail"]


# Тесты kafka и воркера
@pytest.mark.asyncio
@patch("workers.moderation_worker.KafkaProducer")
@patch("workers.moderation_worker.get_pg_connection")
async def test_worker_processes_message_success(
    mock_pg_conn, mock_kafka_producer_class
):
    mock_conn = AsyncMock()
    mock_pg_conn.return_value.__aenter__.return_value = mock_conn

    mock_conn.fetchrow.side_effect = [
        {
            "item_id": 101,
            "seller_id": 202,
            "is_verified_seller": False,
            "name": "Test",
            "description": "Desc",
            "category": 1,
            "images_qty": 0,
        },
        {"id": 50},
    ]

    with patch("workers.moderation_worker.load_model") as mock_load_model, patch(
        "workers.moderation_worker.predict_violation"
    ) as mock_predict:

        mock_load_model.return_value = "mocked_model"
        mock_predict.return_value = {"is_violation": True, "probability": 0.92}

        worker = ModerationWorker(Path("../ml_models/model.pkl"))
        success = await worker.process_message_with_retry({"item_id": 101})

        assert success is True

        update_call = mock_conn.execute.call_args_list[-1]
        assert "UPDATE moderation_results" in update_call[0][0]
        assert update_call[0][1] == True
        assert update_call[0][2] == 0.92
        assert update_call[0][3] == 50


@pytest.mark.asyncio
@patch("workers.moderation_worker.KafkaProducer")
@patch("workers.moderation_worker.get_pg_connection")
async def test_worker_sends_to_dlq_on_error(mock_pg_conn, mock_kafka_producer_class):
    mock_conn = AsyncMock()
    mock_pg_conn.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetchrow.return_value = None

    mock_kafka_instance = AsyncMock()
    mock_kafka_producer_class.return_value = mock_kafka_instance

    worker = ModerationWorker(Path("../ml_models/model.pkl"))

    success = await worker.process_message_with_retry({"item_id": 999})
    assert success is False

    update_call = mock_conn.execute.call_args_list[-1]
    assert "UPDATE moderation_results" in update_call[0][0]
    assert "status = 'failed'" in update_call[0][0]
    assert "error_message" in update_call[0][0]
    assert update_call[0][1] == "Ad with item_id = 999 not found"
    assert update_call[0][2] == 999

    # DLQ
    mock_kafka_instance.send_json.assert_called_once()
    args, _ = mock_kafka_instance.send_json.call_args
    topic, message = args
    assert topic == "moderation_dlq"
    assert message["original_message"]["item_id"] == 999
    assert "not found" in message["error"]
    assert message["retry_count"] == 3


# Тест на retry в kafka
@pytest.mark.asyncio
@patch(
    "workers.moderation_worker.predict_violation",
    side_effect=ConnectionError("ML service is temporarily unavailable"),
)
@patch("workers.moderation_worker.asyncio.sleep", new_callable=AsyncMock)
@patch("workers.moderation_worker.get_pg_connection")
async def test_worker_retries_on_temporary_error(
    mock_pg_conn, mock_sleep, mock_predict
):
    mock_conn = AsyncMock()
    mock_pg_conn.return_value.__aenter__.return_value = mock_conn

    ad_row_data = {
        "item_id": 123,
        "seller_id": 456,
        "is_verified_seller": False,
        "name": "Test Ad",
        "description": "Test description",
        "category": 1,
        "images_qty": 0,
    }

    mock_conn.fetchrow.side_effect = [
        ad_row_data,
        {"id": 99},
        ad_row_data,
        {"id": 99},
        ad_row_data,
        {"id": 99},
    ]

    worker = ModerationWorker(Path(__file__).parent.parent / "ml_models" / "model.pkl")
    await worker.start()

    try:
        success = await worker.process_message_with_retry({"item_id": 123})

        assert success is False  # после трех попыток неуспех
        assert mock_predict.call_count == 3
        assert mock_sleep.call_count == 2

        last_execute_call = mock_conn.execute.call_args_list[-1]
        sql = last_execute_call[0][0]
        assert "UPDATE moderation_results" in sql
        assert "status = 'failed'" in sql
        assert "ML service is temporarily unavailable" in last_execute_call[0][1]

    finally:
        await worker.stop()


# Отправка нескольких запросов с одним item_id
@pytest.mark.asyncio
async def test_multiple_async_predict_same_item(client):
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

    resp1 = client.post("/predict/async_predict", json={"item_id": item_id})
    resp2 = client.post("/predict/async_predict", json={"item_id": item_id})

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
