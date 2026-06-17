import httpx
import os
from dotenv import load_dotenv
 
load_dotenv()
 
API_KEY     = os.getenv('OYLAN_API_KEY')
ASSISTANT_ID = os.getenv('OYLAN_ASSISTANT_ID')
BASE_URL    = os.getenv('OYLAN_BASE_URL', 'https://oylan.nu.edu.kz/api/v1')
 
HEADERS = {
    'Authorization': f'Api-Key {API_KEY}',
    'accept': 'application/json',
}
 
async def send_message(content: str) -> str:
    url = f'{BASE_URL}/assistant/{ASSISTANT_ID}/interactions/'
    data = {'content': content, 'stream': False}
 
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=HEADERS, data=data)
        resp.raise_for_status()
        result = resp.json()
        return result['response']['content']
