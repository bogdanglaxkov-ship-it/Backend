import httpx
import os
from dotenv import load_dotenv

load_dotenv()

TENDERPLAN_API_KEY = os.getenv("TENDERPLAN_API_KEY", "")

HEADERS = {
    "Authorization": f"Bearer {TENDERPLAN_API_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

CANDIDATES = [
    "https://tenderplan.kz/api/search/list",
    "https://tenderplan.kz/api/tenders/getlist",
    "https://api.tenderplan.kz/search/list",
    "https://api.tenderplan.kz/api/search/list",
]

for url in CANDIDATES:
    print(f"\n--- Пробуем: {url} ---")
    try:
        r = httpx.post(url, headers=HEADERS, json={"limit": 3, "offset": 0}, timeout=10)
        print(f"Status: {r.status_code}")
        print(f"Body (первые 300 символов): {r.text[:300]}")
    except Exception as e:
        print(f"Не удалось подключиться: {e}")

print("\n=== ГОТОВО ===")
print("Если хоть один URL вернул 200 и реальные данные — это и есть казахстанский API.")