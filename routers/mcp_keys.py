import os

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from utils.deps import get_current_user
from utils.security import generate_mcp_key

router = APIRouter(prefix="/mcp", tags=["mcp"])

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp/")


@router.get("/key")
async def get_mcp_key(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Возвращает персональный ключ пользователя для MCP-коннекторов, создавая его при первом обращении."""
    if not user.mcp_key:
        user.mcp_key = generate_mcp_key()
        await db.commit()
    return {"server_url": MCP_SERVER_URL, "key": user.mcp_key}


@router.post("/key/rotate")
async def rotate_mcp_key(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Перевыпускает ключ (например, если он утёк) — старый сразу перестаёт работать."""
    user.mcp_key = generate_mcp_key()
    await db.commit()
    return {"server_url": MCP_SERVER_URL, "key": user.mcp_key}
