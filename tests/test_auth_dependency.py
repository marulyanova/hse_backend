import pytest
from fastapi import HTTPException, status
from unittest.mock import AsyncMock, MagicMock, patch

from dependencies.auth import get_current_account
from models.account import AccountPublic
from services.auth import AuthService

import warnings

warnings.filterwarnings("ignore")

pytestmark = [pytest.mark.unit, pytest.mark.auth]


@pytest.fixture
def mock_auth_service():
    service = MagicMock(spec=AuthService)
    return service


@pytest.fixture
def mock_account_repo():
    repo = AsyncMock()
    return repo


# Тесты для dependency get_current_account
@pytest.mark.asyncio
async def test_no_token_raises_401(mock_auth_service, mock_account_repo):
    # отсутствие токена, 401

    with pytest.raises(HTTPException) as exc:
        await get_current_account(
            access_token=None,
            auth_service=mock_auth_service,
            account_repo=mock_account_repo,
        )
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "missing access token" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_invalid_token_raises_401(mock_auth_service, mock_account_repo):
    # невалидный токен, 401

    mock_auth_service.get_account_from_token.return_value = None

    with pytest.raises(HTTPException) as exc:
        await get_current_account(
            access_token="invalid.token",
            auth_service=mock_auth_service,
            account_repo=mock_account_repo,
        )
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "invalid or expired" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_account_not_found_in_db_raises_401(mock_auth_service, mock_account_repo):
    # аккаунт не найден в БД, 401

    fake_account = AccountPublic(id=42, login="user", is_blocked=False)
    mock_auth_service.get_account_from_token.return_value = fake_account
    mock_account_repo.get_account_by_id = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await get_current_account(
            access_token="valid.token",
            auth_service=mock_auth_service,
            account_repo=mock_account_repo,
        )
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_blocked_account_raises_403(mock_auth_service, mock_account_repo):
    # заблокированный аккаунт, 403

    fake_account = AccountPublic(id=42, login="user", is_blocked=False)
    mock_auth_service.get_account_from_token.return_value = fake_account
    mock_account_repo.get_account_by_id = AsyncMock(
        return_value={
            "id": 42,
            "login": "user",
            "password": "hash",
            "is_blocked": True,
        }
    )

    with pytest.raises(HTTPException) as exc:
        await get_current_account(
            access_token="valid.token",
            auth_service=mock_auth_service,
            account_repo=mock_account_repo,
        )
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
    assert "blocked" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_success_returns_account_without_password(
    mock_auth_service, mock_account_repo
):
    # успешный сценарий возвращает аккаунт без пароля

    fake_account = AccountPublic(id=42, login="test_user", is_blocked=False)
    mock_auth_service.get_account_from_token.return_value = fake_account
    mock_account_repo.get_account_by_id = AsyncMock(
        return_value={
            "id": 42,
            "login": "test_user",
            "password": "should_not_be_returned",
            "is_blocked": False,
        }
    )

    result = await get_current_account(
        access_token="valid.token",
        auth_service=mock_auth_service,
        account_repo=mock_account_repo,
    )

    assert isinstance(result, AccountPublic)
    assert result.id == 42
    assert result.login == "test_user"
    assert result.is_blocked is False
    assert not hasattr(result, "password") or getattr(result, "password", None) is None
