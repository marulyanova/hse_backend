import sys
import pytest
from datetime import datetime, timedelta, timezone
from jwt import PyJWTError
import jwt

from pathlib import Path

from hse_backend.services.auth import AuthService
from hse_backend.models.account import Account

import warnings

warnings.filterwarnings("ignore")

pytestmark = [pytest.mark.unit, pytest.mark.auth]


@pytest.fixture
def auth_service():
    return AuthService(secret_key="test-secret-key", token_expire_minutes=5)


@pytest.fixture
def test_account():
    return Account(id=42, login="test_user", password="hashed_pass", is_blocked=False)


# Тесты для сервиса auth
def test_create_access_token_returns_string(auth_service, test_account):
    token = auth_service.create_access_token(test_account)
    assert isinstance(token, str)
    assert len(token) > 0


def test_token_contains_expected_claims(auth_service, test_account):
    token = auth_service.create_access_token(test_account)
    payload = auth_service.verify_token(token)

    assert payload is not None, "Token verification failed - payload is None"
    assert payload["sub"] == str(test_account.id)
    assert payload["login"] == test_account.login
    assert payload["type"] == "access"
    assert "exp" in payload
    assert "iat" in payload


def test_token_expiration():
    # тест истечения токена

    service = AuthService(
        secret_key="test-secret", token_expire_minutes=0
    )  # с 0 истекает сразу
    account = Account(id=1, login="u", password="p")
    token = service.create_access_token(account)
    assert service.verify_token(token) is None

    # cвежий должен работать
    fresh_service = AuthService(secret_key="test-secret", token_expire_minutes=5)
    fresh_token = fresh_service.create_access_token(account)
    assert fresh_service.verify_token(fresh_token) is not None


def test_verify_invalid_token_returns_none(auth_service):
    assert auth_service.verify_token("invalid.token.here") is None
    assert auth_service.verify_token("") is None
    assert auth_service.verify_token("not-a-jwt") is None


def test_verify_token_with_wrong_secret(test_account):
    service1 = AuthService(secret_key="secret-1")
    service2 = AuthService(secret_key="secret-2")
    token = service1.create_access_token(test_account)
    assert service2.verify_token(token) is None


def test_get_account_from_token_success(auth_service, test_account):
    token = auth_service.create_access_token(test_account)
    payload = auth_service.verify_token(token)
    account = auth_service.get_account_from_token(token)

    assert (
        account is not None
    ), f"get_account_from_token returned None. Payload was: {payload}"
    assert account.id == test_account.id
    assert account.login == test_account.login


def test_get_account_from_token_invalid(auth_service):
    assert auth_service.get_account_from_token("bad.token") is None


def test_token_type_check(auth_service, test_account):
    # токен с неправильным типом должен отклоняться

    payload = {
        "sub": str(test_account.id),
        "login": test_account.login,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
        "type": "refresh",  # тут д.б. "access" в положительном случае
    }
    token = jwt.encode(
        payload, auth_service.secret_key, algorithm=auth_service.algorithm
    )

    assert auth_service.verify_token(token) is None
    assert auth_service.get_account_from_token(token) is None


def test_debug_minimal(auth_service, test_account):
    # только создание и проверка токена

    token = auth_service.create_access_token(test_account)
    raw = jwt.decode(
        token,
        auth_service.secret_key,
        algorithms=["HS256"],
        options={"verify_exp": False},
    )

    verified = auth_service.verify_token(token)
    if verified:
        try:
            manual_account = Account(
                id=int(verified["sub"]),
                login=str(verified["login"]),
                password="",
                is_blocked=False,
            )
        except Exception as e:
            import traceback

            sys.stderr.write(traceback.format_exc())

    account = auth_service.get_account_from_token(token)
    assert verified is not None, "verify_token failed"
    assert account is not None, "get_account_from_token failed"
