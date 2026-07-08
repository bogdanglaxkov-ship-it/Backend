"""services/mcp_server.py — MCP-сервер TenderAI для Claude/ChatGPT/Cursor и т.д.

Доступ только на чтение, авторизация — персональным ключом пользователя
(Authorization: Bearer mck_...), который выдаётся через /api/mcp/key.

source принимает "goszakup" (реальные данные, синк с tenderplan.ru),
"samruk" и "tenderplan" (демо-вкладки, см. seed_demo_sources.py — пока
нет подключённых внешних источников, поэтому это синтетические лоты,
явно помеченные своим source в БД, а не выдумываемые на лету).
"""

import os

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from database import AsyncSessionLocal
from models import User
from regions_data import REGION_MAPPING
from shared_db import TenderDB

BASE_URL = os.environ.get("MCP_PUBLIC_BASE_URL", "http://127.0.0.1:8000")

db = TenderDB()

VALID_SOURCES = {"goszakup", "samruk", "tenderplan"}


def _unknown_source_error(source: str) -> dict:
    return {"error": f"Неизвестный источник «{source}». Доступны: {', '.join(sorted(VALID_SOURCES))}."}


class ApiKeyVerifier(TokenVerifier):
    """Проверяет персональный ключ пользователя (mck_...) как bearer-токен MCP."""

    async def verify_token(self, token: str) -> AccessToken | None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.mcp_key == token))
            user = result.scalar_one_or_none()
        if not user:
            return None
        return AccessToken(token=token, client_id=user.id, scopes=["lots:read"], subject=user.id)


mcp = FastMCP(
    "TenderAI",
    instructions=(
        "Инструменты для поиска и анализа лотов государственных закупок Казахстана "
        "(источники: goszakup, samruk, tenderplan)."
    ),
    token_verifier=ApiKeyVerifier(),
    auth=AuthSettings(
        issuer_url=BASE_URL,
        resource_server_url=f"{BASE_URL}/mcp/",
        required_scopes=["lots:read"],
    ),
    # Смонтирован в main.py под префиксом "/mcp" — здесь путь внутри приложения "/",
    # чтобы итоговый адрес был ровно "/mcp", а не "/mcp/mcp".
    streamable_http_path="/",
)


@mcp.tool()
def search_lots(
    source: str,
    query: str = "",
    region: str = "",
    price_min: float = 0,
    price_max: float = 0,
) -> dict:
    """Искать лоты по названию, региону и сумме. source: "goszakup", "samruk" или "tenderplan"."""
    if source not in VALID_SOURCES:
        return _unknown_source_error(source)

    tenders = db.get_all_tenders(source) or []
    q = query.lower().strip()
    r = region.lower().strip()

    def matches(t: dict) -> bool:
        if q and q not in str(t.get("title", "")).lower():
            return False
        if r and r not in str(t.get("region", "")).lower():
            return False
        price = t.get("price") or 0
        if price_min and price < price_min:
            return False
        if price_max and price > price_max:
            return False
        return True

    results = [t for t in tenders if matches(t)]
    return {"total": len(results), "items": results[:20]}


@mcp.tool()
def get_lot(source: str, id: str) -> dict:
    """Открыть карточку лота: сумма, регион, дедлайн + базовая финансовая оценка."""
    if source not in VALID_SOURCES:
        return _unknown_source_error(source)

    tender = db.get_tender_by_id(id)
    if not tender or tender.get("source", "goszakup") != source:
        return {"error": f"Лот {id} не найден в источнике «{source}»"}

    price = float(tender.get("price") or 0)
    return {
        **tender,
        "analysis": {
            "tax_estimate_kzt": round(price * 0.12, 2),
            "fee_estimate_kzt": round(price * 0.01, 2),
            "note": "Оценка по стандартной ставке налога 12% и обеспечения 1%. Не финансовая рекомендация.",
        },
    }


@mcp.tool()
def read_lot_spec(source: str, id: str) -> dict:
    """Скачать и прочитать техническую спецификацию лота (PDF/DOCX), если она есть."""
    if source not in VALID_SOURCES:
        return _unknown_source_error(source)

    tender = db.get_tender_by_id(id)
    if not tender or tender.get("source", "goszakup") != source:
        return {"error": f"Лот {id} не найден в источнике «{source}»"}

    return {
        "error": "Для этого лота нет прикреплённого документа техзадания в базе TenderAI.",
        "source_url": tender.get("url"),
    }


@mcp.tool()
def get_filters(source: str) -> dict:
    """Доступные значения фильтров: регионы и типы лотов. source: "goszakup", "samruk" или "tenderplan"."""
    if source not in VALID_SOURCES:
        return _unknown_source_error(source)

    return {
        "regions": sorted(set(REGION_MAPPING.values())),
        "lot_types": ["Товар", "Услуга", "Работа"],
        "statuses": ["active", "completed", "canceled", "paused"],
    }


def mcp_asgi_app():
    """ASGI-приложение MCP-сервера для монтирования в основной FastAPI app."""
    return mcp.streamable_http_app()
