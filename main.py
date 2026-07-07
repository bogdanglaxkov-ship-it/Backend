


import threading
 
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
 
from database import engine, Base, get_db
from models import Message, User  # noqa: F401 — обязательно, иначе таблица users не создастся
from routers.auth import router as auth_router
from utils.error_handlers import register_validation_exception_handler
 
from services.oylan import send_message, search_tenders_via_web
from tenderplan_sync import start_sync_worker, fetch_tender_details
from shared_db import TenderDB
 
 
# ---------------------------------------------------------------------------
# 1. Lifespan — создаёт таблицы (messages + users) и запускает фоновый поток
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
 
    threading.Thread(target=start_sync_worker, daemon=True).start()
    yield
 
 
# ---------------------------------------------------------------------------
# 2. Инициализация приложения (только один раз!)
# ---------------------------------------------------------------------------
app = FastAPI(lifespan=lifespan)
 
register_validation_exception_handler(app)
app.include_router(auth_router, prefix="/api")
 
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

REGION_MAPPING = {
    "алмат": "Алматы",
    "астан": "Астана",
    "нур-султан": "Астана",
    "шымкент": "Шымкент",
    "акмол": "Акмолинская",
    "актюб": "Актюбинская",
    "атырау": "Атырауская",
    "восточно": "Восточно-Казахстанская",
    "жамбыл": "Жамбылская",
    "западно": "Западно-Казахстанская",
    "караган": "Карагандинская",
    "костан": "Костанайская",
    "кызылорд": "Кызылординская",
    "мангист": "Мангистауская",
    "павлодар": "Павлодарская",
    "северо": "Северо-Казахстанская",
    "туркестан": "Туркестанская",
    "абай": "Абайская",
    "жетысу": "Жетысуская",
    "улытау": "Улытауская"
}

def normalize_region_name(raw_reg: Optional[str]) -> str:
    """Приводит сырой регион из БД к имени, которое ждет фронтенд."""
    if not raw_reg:
        return "Астана"
    raw_lower = str(raw_reg).lower()
    for key, fine_name in REGION_MAPPING.items():
        if key in raw_lower:
            return fine_name
    return "Астана"

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
    return [{"role": m.role, "content": m.content} for m in messages]

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
        reply = await send_message(req.message, history)
        await save_message(req.session_id, "user", req.message, db_session)
        await save_message(req.session_id, "assistant", reply, db_session)
        return {"reply": reply, "session_id": req.session_id}
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
async def get_all_tenders(region: Optional[str] = None, district: Optional[str] = None, keyword: Optional[str] = None):
    """Списочный эндпоинт (GET) тендеров с защитой от 'None'.
    Если по заданным фильтрам локальная база пуста, делаем fallback-запрос через веб-поиск Oylan.
    """
    req_region = clean_val(region)
    req_district = clean_val(district)
    req_keyword = clean_val(keyword)

    all_tenders = db.get_all_tenders() or []
    filtered = all_tenders

    if req_region:
        filtered = [t for t in filtered if t.get("region") and req_region.lower() in str(t["region"]).lower()]
    if req_district:
        filtered = [t for t in filtered if t.get("district") and req_district.lower() in str(t["district"]).lower()]
    if req_keyword:
        filtered = [t for t in filtered if t.get("title") and req_keyword.lower() in str(t["title"]).lower()]

    if not filtered and (req_region or req_district or req_keyword):
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

# ─────────────────────────────────────────────
#  ЖИВАЯ АНАЛИТИКА И ДИНАМИЧЕСКАЯ КАРТА
# ─────────────────────────────────────────────
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