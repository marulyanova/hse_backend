import sys
import pytest
from pathlib import Path
import asyncio

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

HSE_BACKEND_DIR = PROJECT_ROOT / "hse_backend"
if str(HSE_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(HSE_BACKEND_DIR))

from hse_backend.clients.redis import redis_client
from hse_backend.clients.postgres import close_pool
from hse_backend.main import app
from hse_backend.ml_models.model import load_model
from pathlib import Path
import os
from fastapi.testclient import TestClient
from hse_backend.main import app

import pytest_asyncio

import warnings

warnings.filterwarnings("ignore")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# postres pool для интеграционных тестов - создается один раз на сессию и закрывается в конце
@pytest_asyncio.fixture(scope="session", autouse=True)
async def postgres_pool():
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

    async def _connect():
        await redis_client.connect()

    asyncio.run(_connect())
    yield

    async def _close():
        if redis_client._client:
            await redis_client._client.aclose()
            redis_client._connected = False


from hse_backend.repositories.accounts import AccountRepository
from hse_backend.repositories.users import UserRepository
from hse_backend.repositories.ads import AdRepository
import uuid


@pytest_asyncio.fixture(autouse=True)
async def clear_account_cache():
    """Очистка Redis cache для аккаунтов перед каждым тестом, чтобы избежать влияния данных из других тестов"""
    try:
        await redis_client.delete_pattern("account:*")
    except Exception:
        pass

    yield


@pytest.fixture(scope="function")
def authenticated_client(event_loop):
    """Фикстура для аутентифицированного клиента"""

    account_repo = AccountRepository()

    async def setup():
        # Создаем уникальный логин
        unique = str(uuid.uuid4())[:8]
        login = f"test_user_{unique}"
        password = "test_pass_123"

        # Создаем аккаунт
        account = await account_repo.create_account(login=login, password=password)

        # Логинимся с JSON body
        client = TestClient(app)
        response = client.post("/login", json={"login": login, "password": password})
        assert response.status_code == 200

        return client, account["id"]

    client, account_id = event_loop.run_until_complete(setup())
    yield client

    # очистка Redis cache для этого аккаунта после теста, чтобы не влиять на другие тесты
    async def cleanup():
        try:
            await redis_client.delete(f"account:{account_id}")
        except Exception:
            pass

    event_loop.run_until_complete(cleanup())


@pytest.fixture(scope="session", autouse=True)
def setup_app_models():

    BASE_DIR = Path(__file__).resolve().parents[1]
    model_dir = BASE_DIR / "ml_models"
    violation_model_path = model_dir / "model.pkl"

    if os.path.exists(violation_model_path):
        app.state.models = {"violation_model": load_model(violation_model_path)}
    else:
        # для тестов можно просто создать и загрузить фиктивную модель, чтобы не зависеть от реальной модели
        from sklearn.ensemble import RandomForestClassifier
        import numpy as np

        model = RandomForestClassifier(n_estimators=10, random_state=42)
        X = np.random.rand(100, 4)
        y = np.random.randint(0, 2, 100)
        model.fit(X, y)
        app.state.models = {"violation_model": model}


@pytest.fixture()
def clean_redis_cache():
    """
    Фикстура для очистки Redis cache перед каждым тестом, чтобы избежать влияния данных из других тестов.
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
