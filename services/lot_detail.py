"""
lot_detail.py — сборка детальной карточки лота (страница /tenders/{id} на фронте).

TenderDB хранит только базовые поля (id/title/price/region/status/url),
остальное для этой страницы (классификация, заказчик, финансы, документы)
всегда было демо-данными по требованию продукта. Чтобы карточка не "прыгала"
между заходами, все fake-поля детерминированы: sid = hash(tender_id), так что
один и тот же лот всегда даёт одни и те же цифры/документы.
"""

import hashlib
import random

from schemas.tender_schemas import LotDetail, LotDocument

WORKS_RE = "работ|строит|ремонт|монтаж|реконструкц|возвед|благоустрой"
SERVICES_RE = "услуг|обслужива|сопровожд|консалт|аренд|перевозк|охран|клининг|питани|разработ|поддержк"

_CATEGORIES = {
    "works": {
        "label": "Работа",
        "categories": [
            ("Ремонт и строительство зданий", ["Строительство нежилых объектов", "Капитальный ремонт", "Реконструкция здания"]),
            ("Дорожное строительство", ["Ремонт автомобильных дорог", "Строительство инженерных сооружений"]),
        ],
    },
    "services": {
        "label": "Услуга",
        "categories": [
            ("Транспортные услуги", ["Пассажирские перевозки", "Грузовые перевозки"]),
            ("IT-услуги", ["Разработка ПО", "Техническая поддержка"]),
            ("Клининговые и охранные услуги", ["Уборка помещений", "Охрана объекта"]),
        ],
    },
    "goods": {
        "label": "Товар",
        "categories": [
            ("Поставка оборудования", ["Компьютерная техника", "Медицинское оборудование"]),
            ("Поставка материалов", ["Строительные материалы", "Канцелярские товары"]),
        ],
    },
}

_CUSTOMERS = [
    'ГУ "Отдел образования города Астаны"',
    'ГУ "Управление строительства, архитектуры и градостроительства"',
    'КГУ "Дирекция объектов гражданской защиты"',
    'ГУ "Отдел жилищно-коммунального хозяйства"',
    'РГП "Казавтодор"',
    'ГУ "Аппарат акима района"',
    'КГП "Городская поликлиника"',
    'ГУ "Управление пассажирского транспорта и автомобильных дорог"',
]

_LOT_CODES = ["КСПК1", "КСПК2", "ГЗ1", "ГЗ2", "ОК1"]
_TRADE_TYPES = ["Первая закупка", "Повторная закупка"]

_METHODS = {
    "works": ['Конкурс по строительству «под ключ»', "Открытый конкурс с предквалификацией"],
    "services": ["Открытый конкурс", "Запрос ценовых предложений"],
    "goods": ["Запрос ценовых предложений", "Открытый конкурс"],
}

_DOC_TEMPLATES = [
    ("techspec_{n}.pdf", "Приложение 14 (Техническая спецификация закупаемых работ)"),
    ("contract_project_{n2}.pdf", "Проект договора об электронных закупках"),
    ("kspk_doc_{n3}.pdf", "Конкурсная документация"),
    ("kspk_lots_{n3}.pdf", "Приложение 1 (Перечень лотов и условия поставки товаров, выполнения работ, оказания услуг)"),
]
_SHARED_DOC_TEMPLATE = ("appendix_6_kspk_{n3}.pdf", "Приложение 6 (Квалификационные требования, предъявляемые к потенциальному поставщику)")

_STATUS_LABELS = {
    "active": "Опубликовано (приём заявок)",
    "completed": "Завершён",
    "canceled": "Отменён",
    "paused": "На паузе",
}


def _rng(tender_id: str) -> random.Random:
    seed = int(hashlib.md5(tender_id.encode()).hexdigest(), 16)
    return random.Random(seed)


def _classify(title: str) -> str:
    import re

    if re.search(WORKS_RE, title, re.IGNORECASE):
        return "works"
    if re.search(SERVICES_RE, title, re.IGNORECASE):
        return "services"
    return "goods"


def _lot_number(rng: random.Random) -> tuple[str, int]:
    n = rng.randint(10_000_000, 99_999_999)
    return f"{n}-{rng.choice(_LOT_CODES)}", n


def build_lot_detail(tender: dict) -> LotDetail:
    tender_id = str(tender["id"])
    title = tender.get("title") or "Без названия"
    rng = _rng(tender_id)

    lot_type = _classify(title)
    cfg = _CATEGORIES[lot_type]
    category, subcategories = rng.choice(cfg["categories"])
    subcategory = rng.choice(subcategories)

    lot_number, n = _lot_number(rng)
    n2 = rng.randint(10_000_000, 99_999_999)
    n3 = rng.randint(10_000_000, 99_999_999)

    amount = float(tender.get("price") or rng.randint(5, 500) * 1_000_000)
    quantity = 1 if lot_type != "goods" else rng.randint(1, 50)
    price_per_unit = round(amount / quantity, 2)

    margin_percent = round(rng.uniform(8, 32), 1)
    profit = round(amount * margin_percent / 100, 2)
    competition = rng.randint(1, 8)
    dumping_percent = round(rng.uniform(-4, 1.5), 1)

    deadline_days = rng.randint(1, 45)
    deadline_text = f"{deadline_days}д {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"

    documents = [
        LotDocument(id=f"{tender_id}-doc{i}", name=name.format(n=n, n2=n2, n3=n3), description=desc)
        for i, (name, desc) in enumerate(_DOC_TEMPLATES)
    ]
    shared_name, shared_desc = _SHARED_DOC_TEMPLATE
    shared_documents = [
        documents[0],
        LotDocument(id=f"{tender_id}-shared", name=shared_name.format(n3=n3), description=shared_desc),
    ]

    description = (
        f"{title}. Включает выполнение проектных и изыскательских работ, "
        "управление и сопутствующие товары/услуги, необходимые для исполнения контракта."
        if lot_type == "works"
        else f"{title}. Полный объём согласно технической спецификации и конкурсной документации."
    )

    return LotDetail(
        id=tender_id,
        title=title,
        description=description,
        lot_number=lot_number,
        type=cfg["label"],
        category=category,
        subcategory=subcategory,
        customer=tender.get("organization") or rng.choice(_CUSTOMERS),
        customer_rating=rng.randint(35, 96),
        region=tender.get("region"),
        deadline_text=deadline_text,
        status_label=_STATUS_LABELS.get(tender.get("status") or "active", "Опубликовано"),
        purchase_method=rng.choice(_METHODS[lot_type]),
        trade_type=rng.choice(_TRADE_TYPES),
        amount=amount,
        quantity=quantity,
        price_per_unit=price_per_unit,
        margin_percent=margin_percent,
        profit=profit,
        competition=competition,
        dumping_percent=dumping_percent,
        source_url=tender.get("url"),
        documents=documents,
        shared_documents=shared_documents,
    )


def build_lot_chat_context(detail: LotDetail) -> str:
    """Краткая сводка по конкретному лоту для промпта Oylan — используется, когда
    чат на странице лота спрашивает про маржу/риски/заказчика именно этого лота."""
    return (
        f"Данные по лоту «{detail.title}» (номер {detail.lot_number}):\n"
        f"- Тип: {detail.type}, категория: {detail.category} / {detail.subcategory}\n"
        f"- Заказчик: {detail.customer} (рейтинг {detail.customer_rating}/100)\n"
        f"- Регион: {detail.region or '—'}, дедлайн: {detail.deadline_text}, статус: {detail.status_label}\n"
        f"- Метод закупки: {detail.purchase_method}, тип торгов: {detail.trade_type}\n"
        f"- Сумма: {detail.amount:,.0f} тг, количество: {detail.quantity}, цена за единицу: {detail.price_per_unit:,.0f} тг\n"
        f"- Расчётная маржа: {detail.margin_percent}%, прибыль: {detail.profit:,.0f} тг\n"
        f"- Конкуренция: {detail.competition} участник(ов), демпинг: {detail.dumping_percent}%"
    ).replace(",", " ")
