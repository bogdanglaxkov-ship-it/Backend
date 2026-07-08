from fastapi import Depends, Header, HTTPException
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from utils.security import verify_auth_token


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Требуется авторизация")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = verify_auth_token(token)
    except JWTError:
        raise HTTPException(401, "Недействительный токен")

    result = await db.execute(select(User).where(User.id == payload.get("userId")))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(401, "Пользователь не найден")
    return user
