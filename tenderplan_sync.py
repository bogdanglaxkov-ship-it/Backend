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
import sys
import time
import threading
from datetime import datetime
from shared_db import TenderDB

# На Windows консоль по умолчанию открывается в codepage-кодировке (cp1252/cp866),
# которая не умеет печатать ни ✓/✗, ни кириллицу — print() падал с UnicodeEncodeError
# на каждой странице синхронизации, и это тихо проглатывалось в sync_once().
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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


# ─────────────────────────────────────────────
#  СПИСОК РЕГИОНОВ КАЗАХСТАНА
# ─────────────────────────────────────────────
KZ_REGIONS = {
    # Города республиканского значения
    "алматы", "астана", "шымкент", "нур-султан",
    # Области (казахстанские)
    "акмолинская", "актюбинская", "алматинская", "атырауская",
    "восточно-казахстанская", "жамбылская", "западно-казахстанская",
    "карагандинская", "костанайская", "кызылординская", "мангистауская",
    "павлодарская", "северо-казахстанская", "туркестанская",
    "абайская", "жетысуская", "улытауская",
    # Сокращённые варианты
    "акмолинск", "актюбинск", "актобе", "актау", "атырау",
    "семей", "усть-каменогорск", "тараз", "уральск", "кызылорда",
    "жезказган", "петропавловск", "кокшетау", "талдыкорган",
    "туркестан", "жанаозен", "экибастуз", "рудный", "темиртау",
    # Коды страны
    "kz", "казахстан", "kazakhstan",
}

# Соответствие ключевого слова (подстроки) человекочитаемому названию региона РК —
# используется при обогащении гео-данных (см. enrich_missing_geo).
KZ_REGION_NAMES = {
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
    "улытау": "Улытауская",
}


def match_kz_region_name(text: str) -> str | None:
    lower = (text or "").lower()
    for key, name in KZ_REGION_NAMES.items():
        if key in lower:
            return name
    return None

# Ключевые слова, однозначно указывающие на РФ
RF_KEYWORDS = {
    "москва", "санкт-петербург", "спб", "мск", "новосибирск", "екатеринбург",
    "нижний новгород", "казань", "красноярск", "челябинск", "омск",
    "самара", "ростов", "уфа", "волгоград", "краснодар", "воронеж",
    "пермь", "саратов", "тюмень", "тольятти", "ижевск", "барнаул",
    "ульяновск", "владивосток", "ярославль", "иркутск", "хабаровск",
    "россия", "российская федерация", "рф", "russia", "rf",
    "московская", "ленинградская", "свердловская", "тюменская",
    "московск", "росзакупки", "zakupki.gov.ru", "44-фз", "223-фз",
}


def detect_country(raw: dict) -> str:
    """
    Определяет страну тендера. Возвращает 'KZ' или 'RU' или 'OTHER'.
    Проверяет поля: country, countryCode, region, customer_region, и URL.
    """
    # 1. Явный код страны из API
    country_code = str(raw.get("countryCode") or raw.get("country_code") or "").upper()
    if country_code in ("KZ", "398"):
        return "KZ"
    if country_code in ("RU", "643"):
        return "RU"

    # 2. Явное поле country
    country_name = str(raw.get("country") or "").lower().strip()
    if "казахстан" in country_name or "kazakhstan" in country_name or country_name == "kz":
        return "KZ"
    if "россия" in country_name or "russian" in country_name or country_name in ("ru", "рф"):
        return "RU"

    # 3. Проверяем регион
    region_raw = raw.get("region") or raw.get("regionName") or raw.get("customer_region") or ""
    if isinstance(region_raw, dict):
        region_raw = region_raw.get("name") or region_raw.get("title") or ""
    region = str(region_raw).lower().strip()

    # Числовой код региона — это код субъекта РФ (77 = Москва и т.п.),
    # у Казахстана в этом API таких кодов нет.
    if region.isdigit():
        return "RU"

    for kz in KZ_REGIONS:
        if kz in region:
            return "KZ"
    for rf in RF_KEYWORDS:
        if rf in region:
            return "RU"

    # 4. URL / торговая площадка тендера
    platform = raw.get("platform")
    platform_href = platform.get("href") if isinstance(platform, dict) else ""
    url = str(raw.get("url") or raw.get("link") or platform_href or "").lower()
    if "tenderplan.kz" in url or ".kz" in url:
        return "KZ"
    if "zakupki.gov.ru" in url or "zakupki.gov" in url or "roseltorg" in url or ".ru/" in url or url.endswith(".ru"):
        return "RU"

    # 5. Если ничего не определили — считаем KZ
    #    (синкаем с Tenderplan KZ, поэтому по умолчанию KZ)
    return "KZ"


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
#  ШАГ 2.5: детали тендера для карточки на сайте
#  Используем уже подтверждённый рабочий путь fetch_tender_by_id
# ─────────────────────────────────────────────
def fetch_tender_details(tender_id: str) -> dict | None:
    """
    Обёртка над fetch_tender_by_id для main.py.
    Возвращает None если не удалось получить (сайт покажет только локальные данные).
    """
    return fetch_tender_by_id(tender_id)


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
        # 1. Вытаскиваем ID (бывает int или str)
        tender_id = str(raw.get("id") or raw.get("_id") or "")
        
        # 2. Вытаскиваем Название (в Tenderplan это поле 'name')
        title = raw.get("name") or raw.get("title") or raw.get("orderName") or ""
        
        if not tender_id or not title:
            return None

        # 3. Вытаскиваем цену. В коротком списке (/api/search/list) поле называется
        # "maxPrice" (число), а не "price" — на полной модели тендера бывает и "price"
        # как вложенный объект {"value": 123.45, "currency": "KZT"}. Пробуем оба варианта.
        price_raw = raw.get("price")
        if price_raw is None:
            price_raw = raw.get("maxPrice")
        price = None
        if isinstance(price_raw, dict):
            value = price_raw.get("value")
            price = float(value) if value is not None else None
        elif price_raw is not None:
            try:
                price = float(price_raw)
            except (ValueError, TypeError):
                price = None

        # 4. Вытаскиваем регион: в API это может быть строкой или объектом {"id": 1, "name": "Астана"}
        region_raw = raw.get("region")
        region_str = ""
        if isinstance(region_raw, dict):
            region_str = region_raw.get("name") or region_raw.get("title") or ""
        else:
            region_str = str(region_raw or "")

        # 5. Вытаскиваем район (district) — аналогично региону
        district_raw = raw.get("district")
        district_str = ""
        if isinstance(district_raw, dict):
            district_str = district_raw.get("name") or district_raw.get("title") or ""
        else:
            district_str = str(district_raw or "")

        # Определяем страну — если не KZ, отсеиваем
        # Передаем уже очищенную строку региона в detect_country для точности
        raw_for_country = {**raw, "region": region_str}
        country = detect_country(raw_for_country)
        if country != "KZ":
            print(f"[Normalize] Пропускаем не-КЗ тендер ({country}): {title[:60]}")
            return None

        # Определение статуса (1 = active)
        status_map = {1: "active", 2: "canceled", 0: "draft"}
        status = status_map.get(raw.get("status"), "active")

        # Возвращаем плоский чистый словарь для shared_db
        return {
            "id":       tender_id,
            "title":    title,
            "price":    price,
            "region":   region_str.strip(),
            "district": district_str.strip(),
            "status":   status,
            "url":      raw.get("url") or raw.get("link") or f"https://tenderplan.kz/tender/{tender_id}",
            "keyword":  "",
            "country":  "KZ",
        }
    except Exception as e:
        import traceback
        print(f"[Normalize] Критическая ошибка парсинга полей: {e}")
        traceback.print_exc()
        return None


# ─────────────────────────────────────────────
#  ШАГ 4.5: дозагрузка региона/страны по полной модели тендера
# ─────────────────────────────────────────────
# Короткий список (/api/search/list) вообще не содержит локацию — есть только
# в полной модели (/api/tenders/get): числовой код региона (это код субъекта РФ,
# а не РК — большинство тендеров tenderplan.ru реально российские) и текстовые
# адрес/название заказчика внутри вложенной формы. Поэтому страну и регион здесь
# определяем заново по тексту, а не доверяем дефолту "KZ" из normalize().

def _find_delivery_place(node) -> str:
    """Рекурсивно ищет текстовое поле DeliveryPlace во вложенной JSON-форме тендера."""
    if isinstance(node, dict):
        if node.get("fn") == "DeliveryPlace" and isinstance(node.get("fv"), str):
            return node["fv"]
        for value in node.values():
            found = _find_delivery_place(value)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_delivery_place(item)
            if found:
                return found
    return ""


def enrich_missing_geo(limit: int = 80) -> int:
    """Догружает регион/страну для тендеров без региона. Ограничено limit за вызов,
    чтобы не упереться в рейт-лимит Tenderplan и не тормозить обычную синхронизацию.
    """
    db_local = TenderDB()
    ids = db_local.get_tenders_missing_region(limit)
    updated = 0

    for tender_id in ids:
        full = fetch_tender_by_id(tender_id)
        if not full:
            continue

        customers = full.get("customers") or []
        customer_text = " ".join(
            c.get("name", "") for c in customers if isinstance(c, dict)
        )
        delivery_text = ""
        raw_json = full.get("json")
        if isinstance(raw_json, str):
            try:
                delivery_text = _find_delivery_place(json.loads(raw_json))
            except (ValueError, TypeError):
                delivery_text = ""

        combined = f"{customer_text} {delivery_text}"
        region_name = match_kz_region_name(combined)
        country = "KZ" if region_name else detect_country(full)

        db_local.update_geo(tender_id, region_name or "", country)
        updated += 1
        time.sleep(0.3)

    print(f"[Enrich] Обновлено гео-данных: {updated} тендеров (было без региона: {len(ids)})")
    return updated


# ─────────────────────────────────────────────
#  ШАГ 5: полная синхронизация
# ─────────────────────────────────────────────
def sync_once():
    """
    Основная функция синхронизации.
    Игнорируем нерабочий getlist и качаем данные ТОЛЬКО через рабочий поиск.
    """
    print(f"\n============================================================")
    print(f"[Sync] Старт синхронизации — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"============================================================\n")
    
    db = TenderDB()
    keywords = [
        "строительство", "IT", "медицина", "поставка", "услуги",
        "Казахстан", "Алматы", "Астана",
    ]
    total_added = 0

    for kw in keywords:
        print(f"[Sync] Запуск выгрузки по ключевому слову: '{kw}'")
        # Качаем первые 3 страницы по каждому слову (по 50 тендеров на страницу)
        for page in range(1, 4):
            try:
                # ИСПРАВЛЕНО: передаем kw просто как первый аргумент, без query=
                raw_tenders, total_count = search_tenders(kw, page=page, per_page=50)
                
                if not raw_tenders:
                    print(f"[Sync] Нет результатов на странице {page} для '{kw}'")
                    break
                    
                page_added = 0
                for raw in raw_tenders:
                    normalized = normalize(raw)
                    if normalized:
                        # Сохраняем в локальную базу oylan.db
                        success = db.add_tender(normalized)
                        if success:
                            page_added += 1
                            total_added += 1
                
                print(f"[Sync] Страница {page} обработана. Добавлено новых в KZ: {page_added}")
                
                # Задержка, чтобы API Tenderplan не забанил за частые запросы
                time.sleep(1)
                
            except Exception as e:
                print(f"[Sync] Ошибка при обработке страницы {page} для '{kw}': {e}")
                continue

    print(f"\n============================================================")
    print(f"[Sync] Готово! Всего за вызов добавлено/обновлено тендеров: {total_added}")
    print(f"============================================================\n")

    try:
        enrich_missing_geo(limit=120)
    except Exception as e:
        print(f"[Enrich] Ошибка при обогащении гео-данных: {e}")

    # ИСПРАВЛЕНО: возвращаем число, чтобы в принт не выводился None
    return total_added

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