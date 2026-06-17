from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from services.oylan import send_message
 
app = FastAPI()
 
class ChatRequest(BaseModel):
    message: str
 
@app.get("/")
def root():
    return {"message": "Oylan assistant is running!"}
 
@app.get("/health")
def health():
    return {"status": "ok"}
 
@app.post("/chat")
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    try:
        reply = await send_message(req.message)
        return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search")
def search():
    return {"status": "ok"}  

# Было: async def search_tenders_endpoint(filters: TenderFilterRequest):
# Стало:

@app.post("/api/tenders/search")
async def search_tenders_endpoint(filters: dict):
    # Теперь FastAPI принимает любой JSON-объект и не ругается
    return {
        "total_count": 2,
        "items": [
            {
                "id": "tender-101",
                "title": "Поставка офисного оборудования для ГУ",
                "price": 1250000.0,
                "status": "active"
            },
            {
                "id": "tender-102",
                "title": "Разработка веб-сайта государственного органа",
                "price": 4500000.0,
                "status": "completed"
            }
        ]
    }

@app.get("/api/tenders/{tender_id}")
async def get_tender_details(tender_id: str):
    tender = await get_tender_by_id(tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Тендер не найден")
    return tender

@app.post("/api/tenders/{tender_id}/analyze")
async def analyze_tender_with_ai(tender_id: str):
    # 1. Получаем инфу о тендере
    # 2. Отправляем в ИИ (через твой send_message или отдельный промпт)
    # 3. Возвращаем структурированный вердикт
    analysis_result = await run_ai_analysis(tender_id)
    return {"tender_id": tender_id, "ai_verdict": analysis_result}

@app.post("/api/tenders/favorites")
def add_to_favorites(tender_id: str): # или через схему BaseModel
    # Логика сохранения в список избранного
    return {"status": "success", "message": f"Тендер {tender_id} добавлен в избранное"}

@app.get("/api/tenders/favorites")
def get_favorite_tenders():
    # Запрос в БД или список залайканных тендеров
    return {"favorites": [{"id": "tender-101", "title": "Поставка оборудования", "status": "active"}]}

@app.get("/api/tenders/favorites")
def get_favorite_tenders():
    # Запрос в БД или список залайканных тендеров
    return {"favorites": [{"id": "tender-101", "title": "Поставка оборудования", "status": "active"}]}

@app.get("/api/analytics/trends")
def get_market_trends():
    return {
        "top_categories": ["Строительство", "IT-услуги", "Медицина"],
        "average_price_drop_percentage": 14.5,
        "active_tenders_count": 12450
    }

@app.get("/api/analytics/map")
async def get_district_analytics():
    # Отдаем данные по районам Алматы для визуализации
    return {
        "city": "Almaty",
        "total_tenders": 12450,
        "districts": [
            {"name": "Бостандыкский", "tender_count": 3450, "total_budget_kzt": 850000000, "intensity": "high"},
            {"name": "Медеуский", "tender_count": 2900, "total_budget_kzt": 1200000000, "intensity": "high"},
            {"name": "Алмалинский", "tender_count": 2100, "total_budget_kzt": 540000000, "intensity": "medium"},
            {"name": "Ауэзовский", "tender_count": 1500, "total_budget_kzt": 320000000, "intensity": "medium"},
            {"name": "Жетысуский", "tender_count": 950, "total_budget_kzt": 180000000, "intensity": "low"},
            {"name": "Турксибский", "tender_count": 800, "total_budget_kzt": 150000000, "intensity": "low"},
            {"name": "Алатауский", "tender_count": 500, "total_budget_kzt": 95000000, "intensity": "low"},
            {"name": "Наурызбайский", "tender_count": 250, "total_budget_kzt": 40000000, "intensity": "low"}
        ]
    }

@app.post("/api/calculator/margin")
async def calculate_margin(data: dict):
    # Принимает {"tender_price": 1000000, "my_cost": 700000}
    tender_price = data.get("tender_price", 0)
    my_cost = data.get("my_cost", 0)
    
    tax = tender_price * 0.12 # условно 12% НДС
    fee = tender_price * 0.01 # 1% обеспечение
    pure_profit = tender_price - my_cost - tax - fee
    
    return {
        "pure_profit_kzt": pure_profit,
        "margin_percentage": round((pure_profit / tender_price) * 100, 2) if tender_price else 0,
        "roi": "Отличная сделка" if pure_profit > 100000 else "Низкая выгода"
    }

@app.get("/api/tenders/{tender_id}/similar")
async def get_similar_tenders(tender_id: str):
    return {
        "source_tender_id": tender_id,
        "similar_items": [
            {"id": "tender-555", "title": "Закупка серверного оборудования для Налоговой", "price": 18000000.0, "region": "Астана"},
            {"id": "tender-777", "title": "Модернизация IT-инфраструктуры Акимата", "price": 12000000.0, "region": "Алматы"}
        ]
    }
