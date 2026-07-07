from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    password: str = Field(min_length=8, max_length=72)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class PublicUser(BaseModel):
    id: str
    email: EmailStr
    name: str
    email_verified: bool

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    success: bool
    message: str
    user: Optional[PublicUser] = None
    token: Optional[str] = None
    errors: Optional[dict[str, str]] = None
