"""
main.py — FastAPI бэкенд Oylan
Использует shared_db.py — ту же базу что и TGbot.py
"""
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import engine, Base, get_db, Message
from typing import Optional
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from services.oylan import send_message
from tenderplan_sync import start_sync_worker
from shared_db import TenderDB

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # ← временно * чтобы исключить любые проблемы с origins
    allow_credentials=False,  # ← False когда origins="*"
    allow_methods=["*"],
    allow_headers=["*"],
)
 
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создаём таблицы БД
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Запускаем синхронизацию тендеров
    start_sync_worker()
    yield

app = FastAPI(lifespan=lifespan)

db  = TenderDB()  # тот же экземпляр БД что в боте (один файл oylan.db)


# ─────────────────────────────────────────────
#  СХЕМЫ
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
 

# ─────────────────────────────────────────────
#  БАЗОВЫЕ ЭНДПОИНТЫ
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Oylan assistant is running!"}

@app.get("/health")
def health():
    return {"status": "ok"}


# ─────────────────────────────────────────────
#  ФУНКЦИИ ДЛЯ РАБОТЫ С ИСТОРИЕЙ
# ─────────────────────────────────────────────
 
async def get_history(session_id: str, db_session: AsyncSession, limit: int = 50):
    """Получить историю сообщений из БД"""
    result = await db_session.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    messages = result.scalars().all()
    return [{"role": m.role, "content": m.content} for m in messages]
 
 
async def save_message(
    session_id: str, role: str, content: str, db_session: AsyncSession
):
    """Сохранить сообщение в БД"""
    msg = Message(session_id=session_id, role=role, content=content)
    db_session.add(msg)
    await db_session.commit()


# ─────────────────────────────────────────────
#  ЧАТ С ИИ
# ─────────────────────────────────────────────

@app.post("/chat")
async def chat(req: ChatRequest, db_session: AsyncSession = Depends(get_db)):
    """Отправить сообщение ассистенту с историей"""
    if not req.message.strip():
        raise HTTPException(400, detail="Message cannot be empty")
    
    try:
        # Получаем историю сообщений
        history = await get_history(req.session_id, db_session)
        
        # Отправляем сообщение с контекстом истории
        reply = await send_message(req.message, history)
        
        # Сохраняем оба сообщения в БД
        await save_message(req.session_id, "user", req.message, db_session)
        await save_message(req.session_id, "assistant", reply, db_session)
        
        return {"reply": reply, "session_id": req.session_id}
    
    except Exception as e:
        import traceback
        print("=== CHAT ERROR ===")
        traceback.print_exc()          # ← полный traceback в терминал
        print("==================")
        raise HTTPException(500, detail=str(e))
 
 
@app.get("/history/{session_id}")
async def history(session_id: str, db_session: AsyncSession = Depends(get_db)):
    """Получить историю чата по session_id"""
    msgs = await get_history(session_id, db_session, limit=50)
    return {"session_id": session_id, "messages": msgs, "count": len(msgs)}
 
 
# ─────────────────────────────────────────────
#  ТЕНДЕРЫ — ПОИСК (используется и сайтом и ботом)
# ─────────────────────────────────────────────

@app.post("/api/tenders/search")
def search_tenders(req: SearchRequest):
    """
    Единый эндпоинт поиска для сайта и бота.
    Бот также ищет напрямую через shared_db.search_tenders().
    """
    filters = req.filters.model_dump()
    results = db.search_tenders(filters)
    return {
        "total_count": len(results),
        "items": results,
        # Совместимость со старым кодом бота
        "results": results,
    }


# ─────────────────────────────────────────────
#  ТЕНДЕРЫ — CRUD
# ─────────────────────────────────────────────

@app.get("/api/tenders")
def get_all_tenders():
    """Все тендеры. Сайт использует для отображения списка."""
    return {"items": db.get_all_tenders()}


@app.post("/api/tenders")
def create_tender(tender: TenderCreate):
    """
    Добавить тендер в базу.
    Когда сайт добавляет тендер — бот автоматически уведомит подписчиков
    (фоновый поток в TGbot.py проверяет каждую минуту).
    """
    ok = db.add_tender(tender.model_dump())
    if not ok:
        raise HTTPException(500, "Не удалось сохранить тендер")
    return {"status": "created", "id": tender.id}


@app.get("/api/tenders/{tender_id}")
def get_tender(tender_id: str):
    results = db.search_tenders({})
    tender = next((t for t in results if t["id"] == tender_id), None)
    if not tender:
        raise HTTPException(404, "Тендер не найден")
    return tender


# ─────────────────────────────────────────────
#  АНАЛИТИКА
# ─────────────────────────────────────────────

@app.get("/api/analytics/trends")
def get_market_trends():
    tenders = db.get_all_tenders()
    return {
        "total_active": len([t for t in tenders if t.get("status") == "active"]),
        "top_categories": ["Строительство", "IT-услуги", "Медицина"],
        "average_price_drop_percentage": 14.5,
        "active_tenders_count": len(tenders),
    }

@app.get("/api/analytics/map")
def get_district_analytics():
    return {
        "city": "Almaty",
        "total_tenders": 12450,
        "districts": [
            {"name": "Бостандыкский",  "tender_count": 3450, "total_budget_kzt": 850_000_000,  "intensity": "high"},
            {"name": "Медеуский",       "tender_count": 2900, "total_budget_kzt": 1_200_000_000,"intensity": "high"},
            {"name": "Алмалинский",     "tender_count": 2100, "total_budget_kzt": 540_000_000,  "intensity": "medium"},
            {"name": "Ауэзовский",      "tender_count": 1500, "total_budget_kzt": 320_000_000,  "intensity": "medium"},
            {"name": "Жетысуский",      "tender_count": 950,  "total_budget_kzt": 180_000_000,  "intensity": "low"},
            {"name": "Турксибский",     "tender_count": 800,  "total_budget_kzt": 150_000_000,  "intensity": "low"},
            {"name": "Алатауский",      "tender_count": 500,  "total_budget_kzt": 95_000_000,   "intensity": "low"},
            {"name": "Наурызбайский",   "tender_count": 250,  "total_budget_kzt": 40_000_000,   "intensity": "low"},
        ]
    }


# ─────────────────────────────────────────────
#  КАЛЬКУЛЯТОР
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


# ─────────────────────────────────────────────
#  ПОДПИСКИ (для сайта, бот управляет напрямую)
# ─────────────────────────────────────────────

@app.get("/api/subscriptions/{user_id}")
def get_subscription(user_id: int):
    sub = db.get_subscription(user_id)
    if not sub:
        raise HTTPException(404, "Подписка не найдена")
    return sub

@app.get("/api/subscriptions")
def get_all_subscriptions():
    return {"subscriptions": db.get_all_active_subscriptions()}
