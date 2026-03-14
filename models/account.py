from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class Account(BaseModel):
    # модель аккаунта для передачи между слоями приложения

    id: int = Field(..., gt=0)
    login: str = Field(..., min_length=1)
    password: Optional[str] = Field(default=None, min_length=1)
    is_blocked: bool = False

    model_config = ConfigDict(from_attributes=True)


class AccountPublic(BaseModel):
    # публичная модель без пароля

    id: int = Field(..., gt=0)
    login: str = Field(..., min_length=1)
    is_blocked: bool = False

    model_config = ConfigDict(from_attributes=True)
