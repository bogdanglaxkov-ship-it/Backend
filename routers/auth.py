from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from controllers import auth_controller
from database import get_db
from schemas.auth_schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    status_code, result = await auth_controller.register_user(db, payload)
    return JSONResponse(status_code=status_code, content=result.model_dump(exclude_none=True))


@router.post("/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    status_code, result = await auth_controller.login_user(db, payload)
    return JSONResponse(status_code=status_code, content=result.model_dump(exclude_none=True))


@router.post("/verify-email")
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    status_code, result = await auth_controller.verify_email(db, payload)
    return JSONResponse(status_code=status_code, content=result.model_dump(exclude_none=True))


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    status_code, result = await auth_controller.forgot_password(db, payload)
    return JSONResponse(status_code=status_code, content=result.model_dump(exclude_none=True))


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    status_code, result = await auth_controller.reset_password(db, payload)
    return JSONResponse(status_code=status_code, content=result.model_dump(exclude_none=True))


# В main.py подключите так:
#   from routers.auth import router as auth_router
#   app.include_router(auth_router, prefix="/api")
