import os
import time
from fastapi import APIRouter, HTTPException, status, Response
from fastapi.responses import JSONResponse

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.account import Account
from repositories.accounts import AccountRepository
from services.auth import AuthService
from metrics import AUTH_REQUESTS_TOTAL, AUTH_REQUEST_DURATION

router = APIRouter()
account_repo = AccountRepository()
auth_service = AuthService(secret_key=os.getenv("JWT_SECRET_KEY", "dev-secret-key"))


@router.post("/login")
async def login(login: str, password: str, response: Response):
    start = time.time()
    labels = {"status": "unknown"}

    try:
        # ищем аккаунт по логину
        account_data = await account_repo.get_account_by_login(login)

        # проверка, что аккаунт существует
        if not account_data:
            labels["status"] = "invalid_credentials"
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid login or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # проверка пароля
        if account_data["password"] != password:
            labels["status"] = "invalid_credentials"
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid login or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # проверка блокировки
        if account_data.get("is_blocked"):
            labels["status"] = "blocked"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is blocked",
            )

        account = Account(**account_data)
        token = auth_service.create_access_token(account)

        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            secure=os.getenv("ENV", "dev") == "prod",
            samesite="lax",
            max_age=1800,
            path="/",
        )

        labels["status"] = "success"
        return {"message": "Logged in successfully", "user_id": account.id}

    except ValueError as e:
        labels["status"] = "invalid_credentials"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    finally:
        duration = time.time() - start
        AUTH_REQUESTS_TOTAL.labels(**labels).inc()
        AUTH_REQUEST_DURATION.labels(endpoint="/login").observe(duration)
