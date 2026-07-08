"""seed_demo_sources.py — разовое наполнение демо-вкладок "Самрук" и "TenderPlan.Kz".

"Госзакуп" синкается реальными данными из tenderplan.ru (см. tenderplan_sync.py).
У "Самрук" и "TenderPlan.Kz" пока нет подключённого источника — эта функция
наполняет их правдоподобными синтетическими лотами (~100 каждой), чтобы
разделы не были пустыми, пока реальная интеграция не подключена.

Идемпотентно: если во вкладке уже есть записи — повторно не сеет.
"""

import random
import uuid

from regions_data import REGION_MAPPING
from shared_db import TenderDB

REGIONS = sorted(set(REGION_MAPPING.values()))

CITIES_BY_REGION = {
    "Алматы": ["Алмалинский", "Бостандыкский", "Медеуский", "Ауэзовский"],
    "Астана": ["Есильский", "Сарыаркинский", "Алматинский"],
    "Шымкент": ["Абайский", "Аль-Фарабийский"],
}

TEMPLATES = [
    ("Строительство и капитальный ремонт объекта инфраструктуры", "Работа", (150_000_000, 900_000_000)),
    ("Поставка и монтаж медицинского оборудования для стационара", "Работа", (40_000_000, 700_000_000)),
    ("Комплексная поставка и внедрение информационной системы", "Товар", (20_000_000, 700_000_000)),
    ("Поставка автотранспорта и спецтехники", "Товар", (30_000_000, 500_000_000)),
    ("Оказание клининговых услуг для административных зданий", "Услуга", (5_000_000, 60_000_000)),
    ("Поставка продуктов питания для социальных учреждений", "Товар", (3_000_000, 45_000_000)),
    ("Услуги охраны объектов", "Услуга", (4_000_000, 50_000_000)),
    ("Проектно-изыскательские работы по объекту", "Работа", (10_000_000, 120_000_000)),
    ("Поставка канцелярских товаров и оргтехники", "Товар", (1_000_000, 25_000_000)),
    ("Ремонт инженерных сетей и коммуникаций", "Работа", (20_000_000, 180_000_000)),
]

STATUSES = ["active", "active", "active", "paused", "completed"]


def _generate(source: str, count: int) -> list[dict]:
    items = []
    for _ in range(count):
        title_base, keyword, (lo, hi) = random.choice(TEMPLATES)
        region = random.choice(REGIONS)
        district = random.choice(CITIES_BY_REGION.get(region, [region]))
        price = round(random.uniform(lo, hi), -3)
        items.append({
            "id": f"{source}-{uuid.uuid4().hex[:12]}",
            "title": f"{title_base} — {district}, {region}",
            "price": price,
            "region": region,
            "district": district,
            "keyword": keyword,
            "status": random.choice(STATUSES),
            "url": None,
            "country": "KZ",
            "source": source,
        })
    return items


def seed_if_empty(db: TenderDB, source: str, count: int = 100) -> int:
    """Засеивает вкладку, только если она ещё пустая. Возвращает число добавленных записей."""
    if db.count_tenders_by_source(source) > 0:
        return 0
    for tender in _generate(source, count):
        db.add_tender(tender)
    return count


def seed_all(db: TenderDB | None = None) -> None:
    db = db or TenderDB()
    for source in ("samruk", "tenderplan"):
        added = seed_if_empty(db, source)
        if added:
            print(f"[seed] {source}: добавлено {added} демо-лотов")


if __name__ == "__main__":
    seed_all()
