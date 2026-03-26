import os
import time
from fastapi import APIRouter, HTTPException, status, Response
from fastapi.responses import JSONResponse

from hse_backend.models.account import Account, LoginRequest
from hse_backend.repositories.accounts import AccountRepository
from hse_backend.services.auth import AuthService
from hse_backend.metrics import AUTH_REQUESTS_TOTAL, AUTH_REQUEST_DURATION

router = APIRouter()
account_repo = AccountRepository()
auth_service = AuthService(secret_key=os.getenv("JWT_SECRET_KEY", "dev-secret-key"))


@router.post("/login")
async def login(login_request: LoginRequest, response: Response):
    start = time.time()
    labels = {"status": "unknown"}

    try:
        account = await auth_service.authenticate_user(
            account_repo, login_request.login, login_request.password
        )

        if not account:
            labels["status"] = "invalid_credentials"
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid login or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

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

    except HTTPException:
        raise
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
