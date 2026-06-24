import httpx
import os
from dotenv import load_dotenv

load_dotenv()

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