import os
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jwt import (
    PyJWTError,
    InvalidTokenError,
    ExpiredSignatureError,
    InvalidSignatureError,
)

from hse_backend.models.account import Account, AccountPublic


class AuthService:
    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        token_expire_minutes: int = 30,
    ):
        self.secret_key = secret_key or os.getenv("JWT_SECRET_KEY", "dev-secret-key")
        self.algorithm = algorithm
        self.token_expire_minutes = token_expire_minutes

        if not isinstance(self.secret_key, str):
            raise TypeError(f"secret_key must be str, got {type(self.secret_key)}")

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token or not isinstance(token, str):
            print(f"verify_token: empty or invalid token type")
            return None

        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": True},
            )

            # проверка типа токена
            token_type = payload.get("type")
            if token_type != "access":
                print(
                    f"verify_token: wrong token type '{token_type}', expected 'access'"
                )
                return None

            return payload

        except ExpiredSignatureError as e:
            print(f"verify_token: token expired - {e}")
            return None
        except InvalidSignatureError as e:
            print(f"verify_token: invalid signature - {e}")
            return None
        except InvalidTokenError as e:
            print(f"verify_token: InvalidTokenError - {type(e).__name__}: {e}")
            return None
        except Exception as e:
            print(f"verify_token: unexpected error - {type(e).__name__}: {e}")
            return None

    # создать jwt-токен для аккаунта
    def create_access_token(self, account: Account) -> str:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=self.token_expire_minutes
        )

        payload = {
            "sub": str(account.id),
            "login": account.login,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "access",
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def get_account_from_token(self, token: str) -> Optional[AccountPublic]:
        payload = self.verify_token(token)
        if not payload:
            return None

        try:
            return AccountPublic(
                id=int(payload["sub"]),
                login=str(payload["login"]),
                is_blocked=False,
            )
        except (KeyError, ValueError, TypeError, AttributeError):
            return None
