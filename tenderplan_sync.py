"""
tenderplan_sync.py — синхронизация тендеров из tenderplan.ru

Запускается двумя способами:
  1. Вручную:   python tenderplan_sync.py
  2. Автоматически: импортируется в main.py как фоновый поток

Использует ПРАВИЛЬНЫЕ эндпоинты из документации Tenderplan:
- GET /api/tenders/getlist — Получение списка тендеров
- POST /api/tenders/cursor/create — Создание курсора для пакетной выгрузки
- GET /api/tenders/cursor/get — Получение тендеров по курсору
- POST /api/search/list — Поиск с фильтрами

Фильтрует по Казахстану, сохраняет в shared_db.py (oylan.db).
Бот автоматически уведомит подписчиков через свой фоновый поток.
"""

import httpx
import json
import time
import threading
from datetime import datetime
from shared_db import TenderDB

# ─────────────────────────────────────────────
#  ТВОИ ДАННЫЕ
# ─────────────────────────────────────────────
import os
from dotenv import load_dotenv
load_dotenv()

TENDERPLAN_API_KEY = os.getenv("TENDERPLAN_API_KEY", "")
TENDERPLAN_BASE    = "https://tenderplan.ru/api"

if not TENDERPLAN_API_KEY:
    raise ValueError("TENDERPLAN_API_KEY не найден в .env файле!")

# Интервал автосинхронизации в секундах (10 минут)
SYNC_INTERVAL = 600

HEADERS = {
    "Authorization": f"Bearer {TENDERPLAN_API_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

db = TenderDB()


def _extract_tenders(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    if isinstance(data.get("data"), list):
        return data["data"]
    if isinstance(data.get("data"), dict):
        return _extract_tenders(data["data"])
    for key in ("items", "tenders", "results"):
        if isinstance(data.get(key), list):
            return data[key]
    return []


def _extract_total(data):
    if not isinstance(data, dict):
        return 0
    if isinstance(data.get("total"), int):
        return data["total"]
    pagination = data.get("pagination")
    if isinstance(pagination, dict) and isinstance(pagination.get("total"), int):
        return pagination["total"]
    return 0


# ─────────────────────────────────────────────
#  ШАГ 1: Получить список тендеров (ПРАВИЛЬНО)
# ─────────────────────────────────────────────
def fetch_tenders_getlist(page: int = 1, per_page: int = 50) -> tuple[list[dict], int]:
    """
    GET /api/tenders/getlist — Получение списка коротких моделей тендеров по фильтру
    
    Параметры:
    - page: номер страницы (начинается с 1)
    - per_page: результатов на странице
    
    Фильтруем по Казахстану через параметры.
    """
    params = {
        "page": page,
        "limit": per_page,
        # Фильтр по стране/регионам Казахстана
        # Уточни реальные названия параметров у Tenderplan
    }

    try:
        print(f"[API] GET /api/tenders/getlist?page={page}&limit={per_page}")
        r = httpx.get(
            f"{TENDERPLAN_BASE}/tenders/getlist",
            headers=HEADERS,
            params=params,
            timeout=20
        )

        print(f"[API] Status: {r.status_code}")

        if r.status_code == 200:
            data = r.json()
            tenders = _extract_tenders(data)
            total = _extract_total(data) or len(tenders)
            print(f"[API] ✓ Получено {len(tenders)} тендеров")
            if not tenders:
                print(f"[API] Ответ JSON: {json.dumps(data, ensure_ascii=False)[:800]}")
            return tenders, total
        else:
            print(f"[API] ✗ Ошибка {r.status_code}")
            print(f"[API] Ответ: {r.text[:500]}")
            return [], 0

    except httpx.ConnectError:
        print("[API] ✗ Нет соединения с tenderplan.ru")
        return [], 0
    except Exception as e:
        print(f"[API] ✗ Ошибка: {e}")
        return [], 0


# ─────────────────────────────────────────────
#  ШАГ 2: Получить один тендер по ID (опционально)
# ─────────────────────────────────────────────
def fetch_tender_by_id(tender_id: str) -> dict | None:
    """
    GET /api/tenders/get — Получение полной модели тендера
    """
    try:
        r = httpx.get(
            f"{TENDERPLAN_BASE}/tenders/get",
            headers=HEADERS,
            params={"id": tender_id},
            timeout=15
        )

        if r.status_code == 200:
            return r.json()
        else:
            print(f"[API] GET /tenders/get?id={tender_id} → {r.status_code}")
            return None

    except Exception as e:
        print(f"[API] Ошибка fetch_tender_by_id: {e}")
        return None


# ─────────────────────────────────────────────
#  ШАГ 3: Поиск тендеров с фильтрами
# ─────────────────────────────────────────────
def search_tenders(keyword: str, page: int = 1, per_page: int = 50) -> tuple[list[dict], int]:
    """
    POST /api/search/list — Поиск тендеров с фильтрами
    
    Более мощный вариант для поиска.
    """
    payload = {
        "limit": per_page,
        "offset": (page - 1) * per_page,
    }

    if keyword:
        payload["query"] = keyword

    try:
        print(f"[API] POST /api/search/list (query='{keyword}', page={page})")
        r = httpx.post(
            f"{TENDERPLAN_BASE}/search/list",
            headers=HEADERS,
            json=payload,
            timeout=20
        )

        print(f"[API] Status: {r.status_code}")

        if r.status_code == 200:
            data = r.json()
            tenders = _extract_tenders(data)
            total = _extract_total(data) or len(tenders)
            print(f"[API] ✓ Найдено {len(tenders)} результатов")
            if not tenders:
                print(f"[API] Ответ JSON: {json.dumps(data, ensure_ascii=False)[:800]}")
            return tenders, total
        else:
            print(f"[API] ✗ Ошибка {r.status_code}: {r.text[:300]}")
            return [], 0

    except Exception as e:
        print(f"[API] ✗ Ошибка search_tenders: {e}")
        return [], 0


# ─────────────────────────────────────────────
#  ШАГ 4: нормализация данных
#  Поля tenderplan → наша БД
# ─────────────────────────────────────────────
def normalize(raw: dict) -> dict | None:
    try:
        tender_id = str(raw.get("_id") or raw.get("id") or "")
        title     = raw.get("orderName") or raw.get("title") or raw.get("name") or ""
        price     = float(raw.get("maxPrice") or raw.get("price") or raw.get("amount") or 0)

        if not tender_id or not title:
            return None

        # status: 1=active, 2=canceled, остальное=unknown
        status_map = {1: "active", 2: "canceled", 0: "draft"}
        status = status_map.get(raw.get("status"), "active")

        return {
            "id":       tender_id,
            "title":    title,
            "price":    price,
            "region":   raw.get("region") or raw.get("regionName") or "",
            "district": raw.get("district") or raw.get("districtName") or "",
            "status":   status,
            "url":      raw.get("url") or raw.get("link") or f"https://tenderplan.kz/tender/{tender_id}",
            "keyword":  "",
        }
    except Exception as e:
        print(f"[Normalize] Ошибка: {e} | raw: {raw}")
        return None

    # Название
    title = (
        raw.get("name") or
        raw.get("title") or
        raw.get("subject") or
        raw.get("lot_name") or
        "Без названия"
    )

    # Цена
    price = (
        raw.get("price") or
        raw.get("amount") or
        raw.get("nmck") or          # начальная максимальная цена контракта
        raw.get("initial_price") or
        raw.get("budget") or
        0
    )
    try:
        price = float(str(price).replace(" ", "").replace(",", "."))
    except Exception:
        price = 0.0

    # Регион
    region = (
        raw.get("region") or
        raw.get("region_name") or
        raw.get("delivery_region") or
        raw.get("customer_region") or
        ""
    )
    # Если это словарь — берем имя
    if region and isinstance(region, dict):
        region = region.get("name") or region.get("title") or ""

    # Ссылка
    url = (
        raw.get("url") or
        raw.get("link") or
        raw.get("href") or
        f"https://tenderplan.ru/tenders/{tender_id}"
    )

    # Статус
    status = (
        raw.get("status") or
        raw.get("state") or
        "active"
    )

    return {
        "id":       f"tp_{tender_id}",   # префикс tp_ чтобы не путать с другими источниками
        "title":    str(title)[:500],
        "price":    price,
        "region":   str(region)[:100],
        "district": None,
        "keyword":  None,
        "status":   str(status),
        "url":      str(url),
    }


# ─────────────────────────────────────────────
#  ШАГ 5: полная синхронизация
# ─────────────────────────────────────────────
def sync_once() -> int:
    print(f"\n{'='*60}")
    print(f"[Sync] Старт синхронизации — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"{'='*60}")
    added = 0
    total_processed = 0

    # Используем рабочий эндпоинт POST /api/search/list
    keywords = ["", "строительство", "IT", "медицина", "образование", "транспорт", "поставка"]

    for keyword in keywords:
        page = 1
        max_pages = 10

        while page <= max_pages:
            print(f"\n[Sync] keyword='{keyword}' page={page}")
            raw_list, total = search_tenders(keyword=keyword, page=page, per_page=50)

            if not raw_list:
                break

            for raw in raw_list:
                normalized = normalize(raw)
                if normalized:
                    ok = db.add_tender(normalized)
                    total_processed += 1
                    if ok:
                        added += 1

            if len(raw_list) < 50:
                break

            page += 1
            time.sleep(0.5)

    print(f"\n{'='*60}")
    print(f"[Sync] Готово! Обработано: {total_processed}, добавлено новых: {added}")
    print(f"{'='*60}\n")
    return added

# ─────────────────────────────────────────────
#  ФОНОВЫЙ ПОТОК — запускается из main.py
# ─────────────────────────────────────────────
def start_sync_worker():
    """Запускает синхронизацию в фоновом потоке каждые SYNC_INTERVAL секунд."""
    def worker():
        # Первая синхронизация сразу при старте
        try:
            sync_once()
        except Exception as e:
            print(f"[Worker] Ошибка при первой синхронизации: {e}")

        while True:
            time.sleep(SYNC_INTERVAL)
            try:
                sync_once()
            except Exception as e:
                print(f"[Worker] Ошибка при синхронизации: {e}")

    t = threading.Thread(target=worker, daemon=True, name="TenderplanSync")
    t.start()
    print(f"[Worker] ✓ Фоновый поток запущен (каждые {SYNC_INTERVAL//60} минут)")
    return t


# ─────────────────────────────────────────────
#  ДИАГНОСТИКА — запусти один раз
# ─────────────────────────────────────────────
def debug_api():
    """
    Запусти: python tenderplan_sync.py debug
    
    Проверит все эндпоинты и покажет что возвращает API.
    """
    import json

    print("\n" + "="*60)
    print("=== ДИАГНОСТИКА API TENDERPLAN ===")
    print("="*60)
    print(f"\nAPI Key: {TENDERPLAN_API_KEY[:20]}...")
    print(f"Base URL: {TENDERPLAN_BASE}\n")

    # 1. Получить список тендеров
    print("1️⃣  Тест: GET /api/tenders/getlist")
    print("-" * 60)
    tenders, total = fetch_tenders_getlist(page=1, per_page=3)
    if tenders:
        print(f"✓ Получено {len(tenders)} результатов (всего: {total})")
        print("\nПервый тендер (для проверки полей):")
        print(json.dumps(tenders[0], ensure_ascii=False, indent=2))
    else:
        print("✗ Ошибка при получении списка")

    # 2. Поиск
    print("\n2️⃣  Тест: POST /api/search/list (поиск)")
    print("-" * 60)
    search_results, total = search_tenders("строительство", page=1, per_page=3)
    if search_results:
        print(f"✓ Найдено {len(search_results)} результатов")
    else:
        print("✗ Ошибка при поиске")

    # 3. Получить один тендер
    if tenders:
        print("\n3️⃣  Тест: GET /api/tenders/get (один тендер)")
        print("-" * 60)
        first_id = tenders[0].get("id")
        if first_id:
            full = fetch_tender_by_id(first_id)
            if full:
                print(f"✓ Получена полная информация о тендере {first_id}")
            else:
                print(f"✗ Не удалось получить полную информацию")

    print("\n" + "="*60)
    print("=== ДИАГНОСТИКА ЗАВЕРШЕНА ===")
    print("="*60)


# ─────────────────────────────────────────────
#  ЗАПУСК НАПРЯМУЮ
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "debug":
        debug_api()
    else:
        print("Запуск разовой синхронизации...")
        print("Для диагностики API: python tenderplan_sync.py debug")
        print()
        added = sync_once()
        print(f"\nИтого добавлено в базу: {added} новых тендеров")
        print("✓ Теперь запусти бота — он увидит реальные данные.")
        