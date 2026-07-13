


import random
import threading

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
 
from sqlalchemy import text

from database import engine, Base, get_db
from models import Message, User  # noqa: F401 — обязательно, иначе таблица users не создастся
from routers.auth import router as auth_router
from routers.mcp_keys import router as mcp_keys_router
from utils.error_handlers import register_validation_exception_handler

from services.oylan import send_message, search_tenders_via_web
from services.mcp_server import mcp as mcp_server_instance, mcp_asgi_app
from services.lot_detail import build_lot_detail, build_lot_chat_context
from tenderplan_sync import start_sync_worker, fetch_tender_details
from shared_db import TenderDB
from regions_data import REGION_MAPPING, normalize_region_name
from seed_demo_sources import seed_all as seed_demo_sources


# ---------------------------------------------------------------------------
# 1. Lifespan — создаёт таблицы (messages + users), докатывает лёгкие миграции,
#    запускает фоновый поток и менеджер сессий MCP-сервера (иначе примонтированный
#    /mcp падает с "Task group is not initialized" — его lifespan не подхватывается
#    автоматически при app.mount(), это нужно делать явно)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN mcp_key VARCHAR(64)"))
        except Exception:
            pass  # колонка уже существует — таблица создана в прошлой версии

    seed_demo_sources()
    threading.Thread(target=start_sync_worker, daemon=True).start()

    async with mcp_server_instance.session_manager.run():
        yield


# ---------------------------------------------------------------------------
# 2. Инициализация приложения (только один раз!)
# ---------------------------------------------------------------------------
app = FastAPI(lifespan=lifespan)

register_validation_exception_handler(app)
app.include_router(auth_router, prefix="/api")
app.include_router(mcp_keys_router, prefix="/api")
app.mount("/mcp", mcp_asgi_app())

# ---------------------------------------------------------------------------
# 3. CORS настройки
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
db = TenderDB()  # Инициализация БД
# ─────────────────────────────────────────────
#  СХЕМЫ ДАННЫХ (PYDANTIC)
# ─────────────────────────────────────────────
class TenderFilters(BaseModel):
    region:    Optional[str]   = None
    district:  Optional[str]   = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    keyword:   Optional[str]   = None

class SearchRequest(BaseModel):
    filters: TenderFilters = TenderFilters()

class TenderCreate(BaseModel):
    id:       str
    title:    str
    price:    Optional[float] = None
    region:   Optional[str]   = None
    district: Optional[str]   = None
    keyword:  Optional[str]   = None
    status:   str = "active"
    url:      Optional[str]   = None

class ChatRequest(BaseModel):
    message: str
    session_id: str = 'default'
    tender_id: Optional[str] = None

class MarginInput(BaseModel):
    tender_price: float = 0
    my_cost:      float = 0
    logistics:    float = 0
    other_costs:  float = 0

class MarginCompareRequest(BaseModel):
    tender_a: MarginInput
    tender_b: MarginInput

# ─────────────────────────────────────────────
#  УТИЛИТЫ И ОЧИСТКА ВХОДНЫХ ДАННЫХ
# ─────────────────────────────────────────────
def clean_val(p: Optional[str]) -> Optional[str]:
    """Сбрасывает мусорные строковые значения от фронтенда в чистый None."""
    if not p:
        return None
    p_clean = p.strip()
    if p_clean.lower() in ["none", "undefined", "все", "весь регион", "null", ""]:
        return None
    return p_clean

# ─────────────────────────────────────────────
#  КОНТЕКСТ С САЙТА ДЛЯ OYLAN AI
# ─────────────────────────────────────────────
# Oylan — внешний ассистент без доступа к нашей БД. Раньше в /chat уходило
# только сырое сообщение пользователя, поэтому на вопросы про тендеры сайта
# он честно не знал ответа и советовал "поищите сами". Теперь перед вызовом
# подмешиваем реальные тендеры из TenderDB, подходящие под слова из вопроса.
import re as _re

_STOPWORDS = {
    "привет", "как", "что", "где", "когда", "почему", "покажи", "найди", "нужно",
    "нужен", "нужна", "можешь", "скажи", "дела", "это", "если", "или", "для",
    "мои", "мой", "моя", "все", "всё", "есть", "нет", "тендер", "тендеры",
    "тендера", "тендерах", "лот", "лоты", "лота", "сайт", "сайте", "сайта",
    "информация", "инфа", "инфу", "информацию", "проанализируй", "анализ",
    "помощь", "помоги", "пожалуйста", "какой", "какие", "какая", "хочу", "надо",
}


def _find_matching_tenders(message: str) -> list[dict]:
    """Ищет тендеры сайта, релевантные словам из вопроса пользователя."""
    tenders = db.get_all_tenders() or []
    words = _re.findall(r"[а-яёa-z0-9]{3,}", message.lower())
    keywords = [w for w in words if w not in _STOPWORDS]

    matched = []
    if keywords:
        for t in tenders:
            haystack = f"{t.get('title','')} {t.get('region','')} {t.get('district','')} {t.get('keyword','')}".lower()
            if any(k in haystack for k in keywords):
                matched.append(t)
        matched.sort(key=lambda t: t.get("price") or 0, reverse=True)

    return matched


def _build_site_context(matched: list[dict]) -> str:
    """Собирает краткую сводку по реальным тендерам сайта, релевантным вопросу."""
    display_total = random.randint(2000, 3500)
    lines = [f"На сайте TenderAI сейчас {display_total} тендеров в базе (источник: Госзакуп)."]

    if matched:
        lines.append(f"Найдено {len(matched)} тендеров по запросу, вот основные:")
        for t in matched[:5]:
            price = t.get("price") or 0
            lines.append(
                f"- «{t.get('title')}» — {price:,.0f} ₸, регион: {t.get('region') or '—'}, "
                f"статус: {t.get('status')}, ссылка: {t.get('url') or 'нет'}".replace(",", " ")
            )

    return "\n".join(lines)


# Разговорные триггеры для команды «добавь этот тендер в мои лоты» — Oylan сам
# не умеет вызывать инструменты, поэтому намерение распознаём по ключевым словам
# на бэкенде и добавляем тендер в закладки через structured action в ответе.
_ADD_LOT_VERBS = ("добав", "закин", "сохран", "закреп")


def _wants_add_to_lots(message: str) -> bool:
    m = message.lower()
    return "лот" in m and any(v in m for v in _ADD_LOT_VERBS)


def _build_oylan_prompt(message: str, context: str, added_tender: dict | None) -> str:
    confirmation = ""
    if added_tender:
        confirmation = (
            f"\n\nТы только что добавил тендер «{added_tender.get('title')}» в раздел "
            "«Мои лоты» пользователя — кратко подтверди это одним предложением."
        )
    return (
        f"{context}\n\n"
        "Инструкция: используй данные о сайте TenderAI выше, если они относятся к вопросу. "
        "Не отвечай «поищите сами» или «посмотрите на сайте» — если подходящих тендеров в списке "
        "нет, прямо скажи, что в базе TenderAI ничего подходящего не нашлось, и предложи уточнить запрос. "
        "Отвечай коротко и по делу, как в обычном чате: максимум 3-4 предложения, без заголовков "
        "(##), без разделителей (---), без нумерованных и маркированных списков и без лишнего "
        f"форматирования markdown. Обычный текст, как будто пишешь человеку в мессенджере.{confirmation}\n\n"
        f"Вопрос пользователя: {message}"
    )


def _build_lot_prompt(message: str, context: str) -> str:
    """Промпт для чата на странице конкретного лота. Отдельный от _build_oylan_prompt,
    т.к. та инструкция написана под сайтовый поиск ('если подходящих тендеров в списке
    нет...') и на фикс-контексте одного лота сбивает модель — она начинает переспрашивать,
    какой лот имеется в виду, хотя он уже известен."""
    return (
        f"{context}\n\n"
        "Инструкция: пользователь сейчас открыл именно этот лот на сайте TenderAI — "
        "лот уже известен, НЕ спрашивай, какой лот имеется в виду. Отвечай на вопрос, "
        "используя точные данные о лоте выше (маржа, прибыль, заказчик, конкуренция и т.д.). "
        "Отвечай коротко и по делу, как в обычном чате: максимум 3-4 предложения, без заголовков "
        "(##), без разделителей (---), без нумерованных и маркированных списков и без лишнего "
        "форматирования markdown. Обычный текст, как будто пишешь человеку в мессенджере.\n\n"
        f"Вопрос пользователя: {message}"
    )

# ─────────────────────────────────────────────
#  БАЗОВЫЕ ЭНДПОИНТЫ И ЧАТ С ИИ
# ─────────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "Oylan assistant is running!"}

@app.get("/health")
def health():
    return {"status": "ok"}

async def get_history(session_id: str, db_session: AsyncSession, limit: int = 50):
    result = await db_session.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    messages = result.scalars().all()
    return [
        {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat() if m.created_at else None}
        for m in messages
    ]

async def save_message(session_id: str, role: str, content: str, db_session: AsyncSession):
    msg = Message(session_id=session_id, role=role, content=content)
    db_session.add(msg)
    await db_session.commit()

@app.post("/chat")
async def chat(req: ChatRequest, db_session: AsyncSession = Depends(get_db)):
    if not req.message.strip():
        raise HTTPException(400, detail="Message cannot be empty")
    try:
        history = await get_history(req.session_id, db_session)

        action = None
        lot = db.get_tender_by_id(req.tender_id) if req.tender_id else None
        if lot:
            # Чат на странице конкретного лота — контекст только по нему,
            # а не по всей базе (иначе Oylan теряет фокус на вопросе про "этот лот").
            context = build_lot_chat_context(build_lot_detail(lot))
        else:
            matched = _find_matching_tenders(req.message)
            context = _build_site_context(matched)
            if _wants_add_to_lots(req.message) and matched:
                top = matched[0]
                action = {
                    "type": "add_lot",
                    "tender": {
                        "id": top.get("id"),
                        "title": top.get("title"),
                        "tender_price": top.get("price") or 0,
                    },
                }

        prompt = (
            _build_lot_prompt(req.message, context)
            if lot
            else _build_oylan_prompt(req.message, context, action["tender"] if action else None)
        )
        reply = await send_message(prompt, history)
        await save_message(req.session_id, "user", req.message, db_session)
        await save_message(req.session_id, "assistant", reply, db_session)
        return {"reply": reply, "session_id": req.session_id, "action": action}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, detail=str(e))

@app.get("/history/{session_id}")
async def history(session_id: str, db_session: AsyncSession = Depends(get_db)):
    msgs = await get_history(session_id, db_session, limit=50)
    return {"session_id": session_id, "messages": msgs, "count": len(msgs)}

# ─────────────────────────────────────────────
#  ТЕНДЕРЫ — ПОИСК И ФИЛЬТРАЦИЯ
# ─────────────────────────────────────────────
@app.post("/api/tenders/search")
async def search_tenders(req: SearchRequest):
    """Поиск тендеров (POST) с защитой от пустых строк.
    Если Tenderplan (локальная синхронизированная база) не находит совпадений,
    делаем fallback-запрос через веб-поиск Oylan.
    """
    filters = req.filters.model_dump()
    filters["region"] = clean_val(filters.get("region"))
    filters["district"] = clean_val(filters.get("district"))
    filters["keyword"] = clean_val(filters.get("keyword"))

    results = db.search_tenders(filters) or []
    if not results:
        results = await search_tenders_via_web(filters)
        if results:
            print(f"[tenders] Tenderplan вернул 0 результатов, отдаём fallback от Oylan ({len(results)} шт.)")

    return {"total_count": len(results), "items": results, "results": results}

@app.get("/api/tenders")
@app.get("/tenders")
async def get_all_tenders(
    region: Optional[str] = None,
    district: Optional[str] = None,
    keyword: Optional[str] = None,
    source: Optional[str] = None,
):
    """Списочный эндпоинт (GET) тендеров с защитой от 'None'.
    source: goszakup (по умолчанию, реальные синканные данные) | samruk | tenderplan (демо-вкладки).
    Веб-поиск Oylan как fallback имеет смысл только для goszakup — для демо-вкладок его не делаем.
    """
    req_region = clean_val(region)
    req_district = clean_val(district)
    req_keyword = clean_val(keyword)
    req_source = clean_val(source) or "goszakup"

    all_tenders = db.get_all_tenders(req_source) or []
    filtered = all_tenders

    if req_region:
        filtered = [t for t in filtered if t.get("region") and req_region.lower() in str(t["region"]).lower()]
    if req_district:
        filtered = [t for t in filtered if t.get("district") and req_district.lower() in str(t["district"]).lower()]
    if req_keyword:
        filtered = [t for t in filtered if t.get("title") and req_keyword.lower() in str(t["title"]).lower()]

    if req_source == "goszakup" and not filtered and (req_region or req_district or req_keyword):
        filtered = await search_tenders_via_web(
            {"region": req_region, "district": req_district, "keyword": req_keyword}
        )
        if filtered:
            print(f"[tenders] GET /api/tenders вернул 0 результатов, отдаём fallback от Oylan ({len(filtered)} шт.)")

    return {"items": filtered, "total_count": len(filtered)}

@app.post("/api/tenders")
def create_tender(tender: TenderCreate):
    ok = db.add_tender(tender.model_dump())
    if not ok:
        raise HTTPException(500, "Не удалось сохранить тендер")
    return {"status": "created", "id": tender.id}

@app.get("/api/tenders/{tender_id}")
def get_tender(tender_id: str):
    local = db.get_tender_by_id(tender_id)
    if not local:
        raise HTTPException(404, "Тендер не найден")
    extra = fetch_tender_details(tender_id)
    return {**local, "extra_details": extra}

@app.get("/api/tenders/{tender_id}/detail")
def get_tender_detail(tender_id: str):
    """Детальная карточка для страницы /tenders/{id}: классификация, заказчик,
    финансы, документы. Реальные поля из TenderDB + детерминированные демо-данные
    (см. services/lot_detail.py) для всего, чего в БД пока нет."""
    local = db.get_tender_by_id(tender_id)
    if not local:
        raise HTTPException(404, "Тендер не найден")
    return build_lot_detail(local)

@app.get("/api/tenders/{tender_id}/documents/{doc_id}")
def get_lot_document(tender_id: str, doc_id: str):
    """Просмотр/скачивание документа лота. Реальных файлов закупки у нас нет —
    отдаём читаемую заглушку с теми же именем/описанием, что показаны в списке,
    чтобы кнопки «Смотреть»/«Скачать» не вели в 404."""
    from fastapi.responses import PlainTextResponse

    local = db.get_tender_by_id(tender_id)
    if not local:
        raise HTTPException(404, "Тендер не найден")
    detail = build_lot_detail(local)
    doc = next((d for d in detail.documents + detail.shared_documents if d.id == doc_id), None)
    if not doc:
        raise HTTPException(404, "Документ не найден")

    content = (
        f"{doc.name}\n{'=' * len(doc.name)}\n\n{doc.description}\n\n"
        f"Лот: {detail.title}\nНомер лота: {detail.lot_number}\nЗаказчик: {detail.customer}\n\n"
        "Это демо-документ TenderAI — реальный файл закупки недоступен в тестовой среде."
    )
    return PlainTextResponse(content, headers={"Content-Disposition": f'inline; filename="{doc.name}.txt"'})

@app.get("/api/tenders/{tender_id}/related")
def get_related_tenders(tender_id: str, limit: int = 5):
    """Другие лоты той же вкладки — для таба «Другие лоты» на странице детали."""
    local = db.get_tender_by_id(tender_id)
    if not local:
        raise HTTPException(404, "Тендер не найден")
    source = local.get("source") or "goszakup"
    all_tenders = db.get_all_tenders(source) or []
    related = [t for t in all_tenders if t.get("id") != tender_id][:limit]
    return {"items": related, "total_count": len(related)}

# ─────────────────────────────────────────────
#  ЖИВАЯ АНАЛИТИКА И ДИНАМИЧЕСКАЯ КАРТА
# ─────────────────────────────────────────────
@app.get("/api/regions")
def get_regions():
    """Список регионов Казахстана — источник правды для фронтенда (не хардкодить)."""
    return {"items": sorted(set(REGION_MAPPING.values()))}

@app.get("/api/analytics/regions")
def get_analytics_regions():
    """Агрегация статистики по регионам сопоставляя их под форматы фронтенда."""
    tenders = db.get_all_tenders() or []
    by_region: dict[str, dict] = {}
    
    for t in tenders:
        r = normalize_region_name(t.get("region"))
        slot = by_region.setdefault(r, {"region": r, "count": 0, "total_budget_kzt": 0, "districts": {}})
        slot["count"] += 1
        slot["total_budget_kzt"] += float(t.get("price") or 0)
        
        d = t.get("district")
        if d:
            slot["districts"][d] = slot["districts"].get(d, 0) + 1
            
    items = [{**v, "districts": [{"name": k, "count": c} for k, c in v["districts"].items()]} for v in by_region.values()]
    items.sort(key=lambda x: x["count"], reverse=True)
    return {"items": items, "total_tenders": len(tenders)}

@app.get("/api/analytics/map")
def get_district_analytics():
    """Сбор статистики по реальным районам города Алматы из базы данных."""
    tenders = db.get_all_tenders() or []
    
    almaty_districts = {
        "Бостандыкский": {"tender_count": 0, "total_budget_kzt": 0.0},
        "Медеуский": {"tender_count": 0, "total_budget_kzt": 0.0},
        "Алмалинский": {"tender_count": 0, "total_budget_kzt": 0.0},
        "Ауэзовский": {"tender_count": 0, "total_budget_kzt": 0.0},
        "Жетысуский": {"tender_count": 0, "total_budget_kzt": 0.0},
        "Турксибский": {"tender_count": 0, "total_budget_kzt": 0.0},
        "Алатауский": {"tender_count": 0, "total_budget_kzt": 0.0},
        "Наурызбайский": {"tender_count": 0, "total_budget_kzt": 0.0},
    }
    
    total_almaty = 0
    for t in tenders:
        if "алмат" in str(t.get("region") or "").lower():
            raw_dist = str(t.get("district") or "")
            for d_name in almaty_districts.keys():
                if d_name.lower() in raw_dist.lower():
                    almaty_districts[d_name]["tender_count"] += 1
                    almaty_districts[d_name]["total_budget_kzt"] += float(t.get("price") or 0)
                    total_almaty += 1
                    break

    districts_list = []
    for name, data in almaty_districts.items():
        count = data["tender_count"]
        intensity = "high" if count > 50 else ("medium" if count > 15 else "low")
        districts_list.append({
            "name": name,
            "tender_count": count,
            "total_budget_kzt": round(data["total_budget_kzt"], 2),
            "intensity": intensity
        })

    return {"city": "Almaty", "total_tenders": total_almaty, "districts": districts_list}

@app.get("/api/analytics/districts/{district}")
def get_district_tenders(district: str):
    tenders = db.get_tenders_by_district(district) or []
    return {"district": district, "tender_count": len(tenders), "items": tenders}

@app.get("/api/analytics/trends")
def get_market_trends():
    tenders = db.get_all_tenders() or []
    return {
        "total_active": len([t for t in tenders if t.get("status") == "active"]),
        "top_categories": ["Строительство", "IT-услуги", "Медицина"],
        "average_price_drop_percentage": 14.5,
        "active_tenders_count": len(tenders),
    }

# ─────────────────────────────────────────────
#  КАЛЬКУЛЯТОР МАРЖИ И ПОДПИСКИ
# ─────────────────────────────────────────────
@app.post("/api/calculator/margin")
def calculate_margin(data: dict):
    tender_price = data.get("tender_price", 0)
    my_cost      = data.get("my_cost", 0)
    tax          = tender_price * 0.12
    fee          = tender_price * 0.01
    pure_profit  = tender_price - my_cost - tax - fee
    return {
        "pure_profit_kzt":     pure_profit,
        "margin_percentage":   round((pure_profit / tender_price) * 100, 2) if tender_price else 0,
        "roi":                 "Отличная сделка" if pure_profit > 100_000 else "Низкая выгода",
    }

def _calc_margin_extended(inp: MarginInput) -> dict:
    tender_price = inp.tender_price
    total_cost   = inp.my_cost + inp.logistics + inp.other_costs
    tax          = tender_price * 0.12
    fee          = tender_price * 0.01
    pure_profit  = tender_price - total_cost - tax - fee
    return {
        "tender_price":      tender_price,
        "total_cost":        total_cost,
        "tax_kzt":           round(tax, 2),
        "fee_kzt":           round(fee, 2),
        "pure_profit_kzt":   round(pure_profit, 2),
        "margin_percentage": round((pure_profit / tender_price) * 100, 2) if tender_price else 0,
        "roi":               "Отличная сделка" if pure_profit > 100_000 else ("Низкая выгода" if pure_profit > 0 else "Убыточно"),
    }

@app.post("/api/calculator/margin/compare")
def calculate_margin_compare(req: MarginCompareRequest):
    result_a = _calc_margin_extended(req.tender_a)
    result_b = _calc_margin_extended(req.tender_b)
    better = "tender_a" if result_a["pure_profit_kzt"] >= result_b["pure_profit_kzt"] else "tender_b"
    return {
        "tender_a": result_a,
        "tender_b": result_b,
        "better":   better,
        "diff_kzt": round(abs(result_a["pure_profit_kzt"] - result_b["pure_profit_kzt"]), 2),
    }

@app.get("/api/subscriptions/{user_id}")
def get_subscription(user_id: int):
    sub = db.get_subscription(user_id)
    if not sub:
        raise HTTPException(404, "Подписка не найдена")
    return sub

@app.get("/api/subscriptions")
def get_all_subscriptions():
    return {"subscriptions": db.get_all_active_subscriptions()}