from fastapi import Depends, HTTPException, status, Cookie, Request
from typing import Annotated, Optional

from services.auth import AuthService
from repositories.accounts import AccountRepository
from models.account import Account, AccountPublic


def get_auth_service() -> AuthService:
    return AuthService()


def get_account_repo() -> AccountRepository:
    return AccountRepository()


async def get_current_account(
    access_token: Optional[str] = Cookie(default=None, alias="access_token"),
    auth_service: AuthService = Depends(get_auth_service),
    account_repo: AccountRepository = Depends(get_account_repo),
) -> AccountPublic:

    # Dependency для получения аккаунта из токена.

    # проверка наличия токена
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated: missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # валидация токена
    account_public = auth_service.get_account_from_token(access_token)
    if not account_public:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # проверка в бд
    db_account = await account_repo.get_account_by_id(account_public.id)
    if not db_account:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found",
        )

    if db_account.get("is_blocked"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is blocked",
        )

    return AccountPublic(
        id=db_account["id"],
        login=db_account["login"],
        is_blocked=db_account["is_blocked"],
    )


AuthServiceDepend = Annotated[AuthService, Depends(get_auth_service)]
AccountRepoDepend = Annotated[AccountRepository, Depends(get_account_repo)]
CurrentAccount = Annotated[AccountPublic, Depends(get_current_account)]
