import uuid
import pytest
from fastapi.testclient import TestClient
from main import app
from repositories.accounts import AccountRepository

import warnings

warnings.filterwarnings("ignore")

pytestmark = [pytest.mark.integration_acc, pytest.mark.asyncio, pytest.mark.auth]


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def account_repo():
    return AccountRepository()


# Тесты для ручки /login
async def test_login_success(client, account_repo):
    # успешный вход

    unique = str(uuid.uuid4())[:8]
    login = f"test_success_{unique}"
    password = "correct_pass_123"

    account = await account_repo.create_account(login=login, password=password)
    response = client.post("/login", params={"login": login, "password": password})

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == account["id"]
    assert "access_token" in response.cookies


async def test_login_wrong_password(client, account_repo):
    # неправильный пароль, 401

    unique = str(uuid.uuid4())[:8]
    login = f"test_wrong_pass_{unique}"

    await account_repo.create_account(login=login, password="real_password")
    response = client.post("/login", params={"login": login, "password": "wrong"})

    assert response.status_code == 401
    assert "access_token" not in response.cookies


async def test_login_user_not_found(client):
    # неизвестный пользователь, 401

    response = client.post(
        "/login", params={"login": f"nonexistent_{uuid.uuid4()}", "password": "any"}
    )
    assert response.status_code == 401


async def test_login_blocked_account(client, account_repo):
    # заблокированный пользователь, 403

    unique = str(uuid.uuid4())[:8]
    login = f"test_blocked_{unique}"
    account = await account_repo.create_account(
        login=login, password="pass123", is_blocked=True
    )
    response = client.post("/login", params={"login": login, "password": "pass123"})

    assert response.status_code == 403
    assert "blocked" in response.json()["detail"].lower()


async def test_login_empty_credentials(client):
    # пустые креды, 401

    response = client.post("/login", params={"login": "", "password": ""})
    assert response.status_code == 401


async def test_login_sets_cookie_attributes(client, account_repo):
    unique = str(uuid.uuid4())[:8]
    login = f"test_cookie_{unique}"

    await account_repo.create_account(login=login, password="pass")
    response = client.post("/login", params={"login": login, "password": "pass"})

    assert response.status_code == 200
    cookie = response.cookies.get("access_token")
    assert cookie is not None
    assert len(cookie) > 0
