from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.passwords import password_policy_errors
from app.modules.users.schemas import UserResponse


class SetupStatusResponse(BaseModel):
    needs_setup: bool


class InitializeRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str
    organization_name: str | None = Field(default=None, max_length=255)
    ine10_code: str | None = Field(default=None, pattern=r"^[0-9]{10}$")

    @field_validator("password")
    @classmethod
    def password_policy(cls, value: str) -> str:
        if errors := password_policy_errors(value):
            raise ValueError("contrasenya no vàlida: " + "; ".join(errors))
        return value


class InitializeResponse(BaseModel):
    user: UserResponse
