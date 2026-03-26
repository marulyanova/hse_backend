import pytest
import pytest_asyncio
from typing import AsyncGenerator
from hse_backend.clients.postgres import get_pg_connection
from hse_backend.clients.redis import redis_client
from hse_backend.repositories.accounts import AccountRepository
from hse_backend.services.auth import AuthService

import warnings

warnings.filterwarnings("ignore")


pytestmark = [
    pytest.mark.integration,
    pytest.mark.integration_acc,
    pytest.mark.asyncio,
    pytest.mark.auth,
]


@pytest_asyncio.fixture
async def account_repo() -> AsyncGenerator[AccountRepository, None]:
    repo = AccountRepository()
    yield repo


# Удаление всех тестовых пользователей перед запуском
@pytest_asyncio.fixture(autouse=True)
async def cleanup_test_accounts():
    yield
    async with get_pg_connection() as conn:

        rows = await conn.fetch("SELECT id FROM account WHERE login LIKE 'test_%'")
        account_ids = [row["id"] for row in rows]

        for account_id in account_ids:
            try:
                await redis_client.delete(f"account:{account_id}")
            except Exception:
                pass

        await conn.execute("DELETE FROM account WHERE login LIKE 'test_%'")


# тесты для AccountRepository
async def test_create_account_success(account_repo: AccountRepository):
    # успешное создание аккаунта

    login = "test_user_1"
    password = "qwerty"

    result = await account_repo.create_account(login, password)

    assert result["id"] is not None
    assert result["login"] == login
    # Password is now hashed (SHA256), not plaintext
    assert result["password"] == AuthService.hash_password(password)
    assert result["is_blocked"] is False


async def test_create_account_duplicate_login(account_repo: AccountRepository):
    # проверка, что нельзя два одинаковых логина

    login = "test_duplicated_user"
    password = "qwertyuiop"

    first = await account_repo.create_account(login, password)

    try:
        second = await account_repo.create_account(login, "another_password")
        print(f"No exception, Second account: {second}")
        pytest.fail(f"Expected exception for duplicate login, but got: {second}")
    except Exception as e:
        print(f"Exception raised: {type(e).__name__}: {e}")
        assert "unique" in str(e).lower() or "duplicate" in str(e).lower()


async def test_get_account_by_id_found(account_repo: AccountRepository):
    # поиск аккаунта по ID

    created = await account_repo.create_account("test_by_id", "123456")

    found = await account_repo.get_account_by_id(created["id"])

    assert found is not None
    assert found["id"] == created["id"]
    assert found["login"] == "test_by_id"


async def test_get_account_by_id_not_found(account_repo: AccountRepository):
    # поиск несуществующего аккаунта по ID

    result = await account_repo.get_account_by_id(999999)
    assert result is None


async def test_get_account_by_login_found(account_repo: AccountRepository):
    # поиск аккаунта по логину

    await account_repo.create_account("test_login_search", "123456")

    found = await account_repo.get_account_by_login("test_login_search")

    assert found is not None
    assert found["login"] == "test_login_search"


async def test_get_account_by_login_password_success(account_repo: AccountRepository):
    # авторизация использует AuthService.authenticate_user()

    account = await account_repo.create_account("test_auth_ok", "123456")

    # Verify that the password is hashed in the database
    assert account["password"] == AuthService.hash_password("123456")


async def test_get_account_by_login_password_wrong_password(
    account_repo: AccountRepository,
):
    # Test that stored account has hashed password

    account = await account_repo.create_account("test_auth_bad_pass", "123456")

    # Verify password is hashed
    assert account["password"] != "123456"
    assert account["password"] == AuthService.hash_password("123456")


async def test_get_account_by_login_password_blocked_account(
    account_repo: AccountRepository,
):
    # авторизация, блокировка аккаунта
    created = await account_repo.create_account("test_blocked_auth", "123456")
    await account_repo.block_account(created["id"])

    # Verify account is blocked
    blocked_account = await account_repo.get_account_by_id(created["id"])
    assert blocked_account["is_blocked"] is True


async def test_block_account_success(account_repo: AccountRepository):
    # блокировка

    created = await account_repo.create_account("test_block", "1234")

    result = await account_repo.block_account(created["id"])
    assert result is True

    # акк действительно в блоке
    updated = await account_repo.get_account_by_id(created["id"])
    assert updated["is_blocked"] is True


async def test_block_account_not_found(account_repo: AccountRepository):
    # блокировка несуществующего аккаунта
    result = await account_repo.block_account(999999)
    assert result is False


async def test_delete_account_success(account_repo: AccountRepository):
    # успешное удаление аккаунта

    created = await account_repo.create_account("test_delete", "12345")

    result = await account_repo.delete_account(created["id"])
    assert result is True

    # проверка, что аккаунт удалён
    found = await account_repo.get_account_by_id(created["id"])
    assert found is None


async def test_delete_account_not_found(account_repo: AccountRepository):
    # удаление несуществующего аккаунта
    result = await account_repo.delete_account(999999)
    assert result is False


async def test_validation(account_repo: AccountRepository):
    # пустой логин
    with pytest.raises(ValueError):
        await account_repo.create_account("", "password")

    # невалидный ID
    with pytest.raises(ValueError):
        await account_repo.get_account_by_id(-1)
    with pytest.raises(ValueError):
        await account_repo.get_account_by_id(0)
