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
from models.advertisement import Advertisement
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
@pytest.mark.parametrize("invalid_user_id", [-1, 0, -999])
async def test_user_repository_create_invalid_user_id(invalid_user_id):
    # user_id < 0 некорректны

    repo = UserRepository()
    with pytest.raises(ValueError, match="user_id must be a positive integer"):
        await repo.create_user(user_id=invalid_user_id, is_verified=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_user_id", ["", "abc", None, 1.23])
async def test_user_repository_create_invalid_type_user_id(invalid_user_id):
    # user_id не является целым числом

    repo = UserRepository()
    with pytest.raises(TypeError, match="user_id must be an integer"):
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
@pytest.mark.parametrize("invalid_item_id", [-1, 0, -999])
async def test_create_ad_with_incorrect_item_id(invalid_item_id):
    # попытка создать объявление с некорректным item_id

    user_repo = UserRepository()
    ad_repo = AdRepository()

    seller_id = 12345
    await user_repo.create_user(seller_id, is_verified=True)

    with pytest.raises(ValueError, match="item_id must be a positive integer"):
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
