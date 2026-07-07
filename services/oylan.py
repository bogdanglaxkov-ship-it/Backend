import httpx
import json
import logging
import os
import re
import uuid
from dotenv import load_dotenv
from pydantic import ValidationError

from schemas.tender_schemas import TenderOut

load_dotenv()

logger = logging.getLogger(__name__)

API_KEY = os.getenv('OYLAN_API_KEY')
ASSISTANT_ID = os.getenv('OYLAN_ASSISTANT_ID')
BASE_URL = os.getenv('OYLAN_BASE_URL', 'https://oylan.nu.edu.kz/api/v1')

HEADERS = {
    'Authorization': f'Api-Key {API_KEY}',
    'accept': 'application/json',
}

async def send_message(content: str, history: list[dict] | None = None) -> str:
    url = f'{BASE_URL}/assistant/{ASSISTANT_ID}/interactions/'
    
    # Правильно форматируем историю
    context_parts = []
    if history:
        for msg in history:
            prefix = 'User' if msg['role'] == 'user' else 'Assistant'
            context_parts.append(f"{prefix}: {msg['content']}")
    
    # Добавляем новое сообщение
    context_parts.append(f'User: {content}')
    full_content = '\n'.join(context_parts)
    
    data = {'content': full_content, 'stream': False}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=HEADERS, data=data)
# Логируем чтобы видеть реальный ответ
    print(f"[oylan] status: {r.status_code}")
    print(f"[oylan] response: {r.text}")
    
    r.raise_for_status()
    
    body = r.json()
    
    # Пробуем разные варианты структуры ответа
    if isinstance(body, dict):
        if 'response' in body and isinstance(body['response'], dict):
            return body['response'].get('content', '')
        if 'content' in body:
            return body['content']
        if 'message' in body:
            return body['message']
        if 'text' in body:
            return body['text']
        if 'answer' in body:
            return body['answer']
    
    if isinstance(body, str):
        return body

    return str(body)


# ---------------------------------------------------------------------------
# Fallback: поиск тендеров через веб-поиск ассистента Oylan
# ---------------------------------------------------------------------------
# Используется, когда локальная база (синхронизированная из Tenderplan) не находит
# совпадений по заданным фильтрам. Это генерация LLM по открытым источникам, а не
# проверенные данные Tenderplan — поэтому при любой ошибке или невалидном ответе
# безопасно возвращаем пустой список, не роняя эндпоинт поиска.

_SEARCH_SYSTEM_PROMPT = (
    "Ты — помощник по поиску государственных тендеров и закупок в Казахстане. "
    "Найди в открытых источниках интернета актуальные, реально существующие тендеры, "
    "подходящие под запрос ниже. Ответь ТОЛЬКО JSON-массивом (без markdown, без пояснений), "
    "где каждый элемент имеет поля: title (строка, обязательно), price (число в KZT или null), "
    "region (строка или null), district (строка или null), "
    "status (одно из: active, completed, canceled, paused), url (ссылка на источник или null), "
    "deadline (дата в формате YYYY-MM-DD или null), description (краткое описание или null). "
    "Если ничего подходящего не нашёл — верни пустой массив []. "
    "Не придумывай несуществующие тендеры: если не уверен, что тендер реален — не включай его в ответ."
)


def _build_search_query(filters: dict) -> str:
    parts = []
    if filters.get("keyword"):
        parts.append(f"ключевое слово: {filters['keyword']}")
    if filters.get("region"):
        parts.append(f"регион: {filters['region']}")
    if filters.get("district"):
        parts.append(f"район: {filters['district']}")
    if filters.get("price_min"):
        parts.append(f"цена от: {filters['price_min']}")
    if filters.get("price_max"):
        parts.append(f"цена до: {filters['price_max']}")
    criteria = "; ".join(parts) if parts else "любые актуальные тендеры"
    return f"Найди тендеры по критериям — {criteria}"


def _extract_json_array(text: str) -> list:
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
    return json.loads(text)


async def search_tenders_via_web(filters: dict) -> list[dict]:
    """Fallback-поиск тендеров через веб-поиск ассистента Oylan."""
    query = _build_search_query(filters)
    try:
        reply = await send_message(f"{_SEARCH_SYSTEM_PROMPT}\n\n{query}")
        raw_items = _extract_json_array(reply)
    except Exception as e:
        logger.warning(f"[oylan-fallback] web search failed: {e}")
        return []

    if not isinstance(raw_items, list):
        return []

    tenders = []
    for raw in raw_items:
        if not isinstance(raw, dict) or not raw.get("title"):
            continue
        try:
            tender = TenderOut(
                id=str(uuid.uuid4()),
                title=raw.get("title"),
                price=raw.get("price"),
                region=raw.get("region"),
                district=raw.get("district"),
                status=raw.get("status") or "active",
                url=raw.get("url"),
                deadline=raw.get("deadline"),
                description=raw.get("description"),
            )
        except ValidationError as e:
            logger.warning(f"[oylan-fallback] skipping invalid item: {e}")
            continue
        tenders.append(tender.model_dump())

    return tenders