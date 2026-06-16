from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

# Добавляем новые поля в модель данных
class ChatRequest(BaseModel):
    message: str
    product: Optional[str] = "Услуги"  # Поле для названия товара (необязательное)
    price: Optional[float] = "Техника"   # Поле для цены (необязательное)

@app.get("/")
def root():
    return {"message": "Oylan assistant is running!"}

@app.get("/health")
def health():
    return {"health": "ok"}

@app.post("/chat")
def chat(req: ChatRequest):
    # Формируем красивый ответ в зависимости от того, передан ли товар
    reply_text = f"You said: {req.message}"
    if req.product:
        reply_text += f" | Товар: {req.product}"
    if req.price:
        reply_text += f" (Цена: {req.price})"
        
    return {"reply": reply_text}

@app.post("/chat/send")
def chat_send(req: ChatRequest):  # Переименовали функцию и добавили req
    return {
        "status": "ok", 
        "sent_message": req.message, 
        "product_info": {"name": req.product, "price": req.price}
    }

"""
ChartVision AI - Веб-приложение для технического анализа графиков криптовалют и акций.
Использует Anthropic Claude 3.5 Sonnet с Vision API для анализа скриншотов.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database import init_db
from routers import analysis

# Инициализация приложения с жизненным циклом
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения."""
    # Стартап
    print("🚀 Инициализация ChartVision AI...")
    init_db()
    print("✅ База данных готова!")
    yield
    # Шатдаун
    print("🛑 Завершение работы приложения...")


# Создание приложения
app = FastAPI(
    title="ChartVision AI",
    description="AI-ассистент для технического анализа графиков криптовалют и акций",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене ограничить!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(
    analysis.router,
    prefix="/api/v1/analysis",
    tags=["Анализ графиков"],
)


# Root endpoint
@app.get("/", tags=["Информация"])
async def root():
    """Информация о приложении."""
    return {
        "name": "ChartVision AI",
        "version": "1.0.0",
        "status": "✨ Готово к анализу графиков!",
        "docs_url": "/docs"
    }


@app.get("/health", tags=["Здоровье"])
async def health_check():
    """Проверка здоровья приложения."""
    return {"status": "healthy", "service": "ChartVision AI"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "chartvision_main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

