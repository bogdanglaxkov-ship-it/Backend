"""
TGbot.py — Oylan Tender Bot
Особенности:
  - Динамические кнопки внизу меняются по разделу
  - Подписки с мгновенными уведомлениями (фоновый поток)
  - Единая база тендеров с main.py через shared_db.py
"""

import os
import threading
import time
import httpx
from telebot import types, TeleBot
from dotenv import load_dotenv
from shared_db import TenderDB  # общая БД с main.py

load_dotenv()

BOT_TOKEN   = os.getenv("BOT_TOKEN")
MY_ID       = int(os.getenv("MY_ID", "0"))
FASTAPI_URL = os.getenv("FASTAPI_URL", "http://127.0.0.1:8000")

bot = TeleBot(BOT_TOKEN)
db  = TenderDB()  # единственный экземпляр, тот же что использует main.py

# ─────────────────────────────────────────────────────────
#  СОСТОЯНИЕ ПОЛЬЗОВАТЕЛЯ
#  section: main | region | district | price | keyword | subscribe
# ─────────────────────────────────────────────────────────
class UserState:
    def __init__(self):
        self.section     = "main"
        self.filters     = {"region": None, "district": None,
                            "price_min": None, "price_max": None, "keyword": None}
        self.sub_active  = False   # подписка включена?
        self.price_step  = None    # "min" | "max"  при ручном вводе

states: dict[int, UserState] = {}

def st(uid: int) -> UserState:
    if uid not in states:
        states[uid] = UserState()
        # Восстанавливаем сохранённые фильтры из БД если есть
        saved = db.get_subscription(uid)
        if saved:
            states[uid].filters = saved["filters"]
            states[uid].sub_active = saved["active"]
    return states[uid]

# ─────────────────────────────────────────────────────────
#  РЕГИОНЫ
# ─────────────────────────────────────────────────────────
REGIONS = {
    "Астана":         ["Сарыарка", "Байконыр", "Есиль"],
    "Алматы":         ["Алатауский", "Алмалинский", "Бостандыкский", "Медеуский"],
    "Шымкент":        ["Абайский", "Аль-Фарабийский", "Каратауский"],
    "Акмолинская":    ["Аккольский", "Атбасарский", "Буландынский"],
    "Актюбинская":    ["Айтекебийский", "Алгинский", "Иргизский"],
    "Атырауская":     ["Атырауский", "Индерский", "Исатайский"],
    "ВКО":            ["Абайский", "Аягозский", "Глубоковский"],
    "Жамбылская":     ["Байзакский", "Жамбылский", "Кордайский"],
    "Карагандинская": ["Абайский", "Актогайский", "Каркаралинский"],
    "Костанайская":   ["Алтынсаринский", "Аулиекольский", "Денисовский"],
    "Кызылординская": ["Аральский", "Жалагашский", "Казалинский"],
    "Мангистауская":  ["Бейнеуский", "Каракиянский", "Мунайлинский"],
    "Павлодарская":   ["Аксуский", "Баянаульский", "Железинский"],
    "СКО":            ["Айыртауский", "Акжарский", "Есильский"],
    "Туркестанская":  ["Арысский", "Байдибекский", "Казыгуртский"],
    "ЗКО":            ["Акжаикский", "Бурлинский", "Жангалинский"],
    "Улытауская":     ["Джезказганский", "Сатпаев", "Улытауский"],
}

PRICE_PRESETS = [
    ("До 1 млн",      0,         1_000_000),
    ("1–5 млн",       1_000_000, 5_000_000),
    ("5–20 млн",      5_000_000, 20_000_000),
    ("20–100 млн",    20_000_000,100_000_000),
    ("Свыше 100 млн", 100_000_000, 0),
]

# ─────────────────────────────────────────────────────────
#  ДИНАМИЧЕСКИЕ КЛАВИАТУРЫ (ReplyKeyboard — кнопки снизу)
# ─────────────────────────────────────────────────────────

def kb_main(s: UserState) -> types.ReplyKeyboardMarkup:
    sub_label = "🔔 Подписка: ВКЛ" if s.sub_active else "🔕 Подписка: ВЫКЛ"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton("🔍 Искать"),
        types.KeyboardButton("⚙️ Фильтры"),
    )
    kb.add(
        types.KeyboardButton("🗺 Регион"),
        types.KeyboardButton("💰 Цена"),
    )
    kb.add(
        types.KeyboardButton(sub_label),
        types.KeyboardButton("📋 Мои фильтры"),
    )
    kb.add(types.KeyboardButton("🔄 Сбросить всё"))
    return kb

def kb_regions() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for r in REGIONS:
        kb.add(types.KeyboardButton(r))
    kb.add(types.KeyboardButton("🌍 Все регионы"))
    kb.add(types.KeyboardButton("◀️ Назад"))
    return kb

def kb_districts(region: str) -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for d in REGIONS.get(region, []):
        kb.add(types.KeyboardButton(d))
    kb.add(types.KeyboardButton("📍 Весь регион"))
    kb.add(types.KeyboardButton("◀️ Назад"))
    return kb

def kb_price() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for label, *_ in PRICE_PRESETS:
        kb.add(types.KeyboardButton(label))
    kb.add(types.KeyboardButton("✏️ Ввести вручную"))
    kb.add(types.KeyboardButton("◀️ Назад"))
    return kb

# ─────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────

def only_me(msg) -> bool:
    if msg.from_user.id != MY_ID:
        bot.reply_to(msg, "Бот приватный.")
        return False
    return True

def fmt(v) -> str:
    return f"{v:,} ₸".replace(",", " ") if v else "не указано"

def filters_text(s: UserState) -> str:
    f = s.filters
    sub = "✅ включена" if s.sub_active else "❌ выключена"
    return (
        f"📍 Регион:  {f['region'] or 'Все'}\n"
        f"📌 Район:   {f['district'] or 'Весь'}\n"
        f"💰 От:      {fmt(f['price_min'])}\n"
        f"💰 До:      {fmt(f['price_max'])}\n"
        f"🔑 Слово:   {f['keyword'] or '—'}\n"
        f"🔔 Подписка: {sub}"
    )

def go_main(uid: int, text: str):
    """Переходим в главный раздел."""
    s = st(uid)
    s.section = "main"
    bot.send_message(uid, text, reply_markup=kb_main(s), parse_mode="Markdown")

# ─────────────────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(m):
    if not only_me(m): return
    s = st(m.from_user.id)
    s.section = "main"
    bot.send_message(
        m.chat.id,
        "👋 *Oylan — бот для госзакупок*\n\n"
        "Настрой фильтры → нажми *🔍 Искать*\n"
        "Включи подписку → получай уведомления о новых тендерах автоматически.",
        parse_mode="Markdown",
        reply_markup=kb_main(s)
    )

# ─────────────────────────────────────────────────────────
#  ГЛАВНЫЙ ОБРАБОТЧИК ТЕКСТА
# ─────────────────────────────────────────────────────────

@bot.message_handler(func=lambda m: True)
def router(m):
    if not only_me(m): return
    uid  = m.from_user.id
    s    = st(uid)
    text = m.text.strip()

    # ── Кнопка НАЗАД — всегда возвращает в main ──────────
    if text == "◀️ Назад":
        go_main(uid, "Главное меню:")
        return

    # ── Диспетчер по разделу ─────────────────────────────
    if s.section == "main":
        _handle_main(uid, s, text)

    elif s.section == "region":
        _handle_region(uid, s, text)

    elif s.section == "district":
        _handle_district(uid, s, text)

    elif s.section == "price":
        _handle_price(uid, s, text)

    elif s.section == "price_manual":
        _handle_price_manual(uid, s, text)

    elif s.section == "keyword":
        _handle_keyword(uid, s, text)

    else:
        go_main(uid, "Главное меню:")

# ─────────────────────────────────────────────────────────
#  РАЗДЕЛЫ
# ─────────────────────────────────────────────────────────

def _handle_main(uid, s, text):
    if text == "🔍 Искать":
        bot.send_message(uid, f"⏳ Ищу тендеры...\n\n{filters_text(s)}")
        _do_search(uid, s)

    elif text == "⚙️ Фильтры":
        s.section = "keyword"
        bot.send_message(uid,
            f"*Текущие фильтры:*\n\n{filters_text(s)}\n\n"
            "Введи *ключевое слово* (или `-` чтобы убрать):",
            parse_mode="Markdown",
            reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True)
                .add(types.KeyboardButton("◀️ Назад"))
        )

    elif text == "🗺 Регион":
        s.section = "region"
        bot.send_message(uid, "📍 Выбери регион:", reply_markup=kb_regions())

    elif text == "💰 Цена":
        s.section = "price"
        bot.send_message(uid, "💰 Выбери диапазон цены:", reply_markup=kb_price())

    elif text in ("🔔 Подписка: ВКЛ", "🔕 Подписка: ВЫКЛ"):
        _toggle_subscription(uid, s)

    elif text == "📋 Мои фильтры":
        bot.send_message(uid, f"*Текущие фильтры:*\n\n{filters_text(s)}",
                        parse_mode="Markdown", reply_markup=kb_main(s))

    elif text == "🔄 Сбросить всё":
        for k in s.filters:
            s.filters[k] = None
        s.sub_active = False
        db.save_subscription(uid, s.filters, False)
        go_main(uid, "✅ Всё сброшено.")

    else:
        # Свободный текст = быстрый поиск
        s.filters["keyword"] = text
        bot.send_message(uid, f"🔍 Быстрый поиск: *{text}*...", parse_mode="Markdown")
        _do_search(uid, s)


def _handle_region(uid, s, text):
    if text == "🌍 Все регионы":
        s.filters["region"] = None
        s.filters["district"] = None
        go_main(uid, "✅ Регион: *Все регионы*")
        return
    if text in REGIONS:
        s.filters["region"] = text
        s.filters["district"] = None
        s.section = "district"
        bot.send_message(uid, f"📍 Регион: *{text}*\n\nВыбери район:",
                        parse_mode="Markdown", reply_markup=kb_districts(text))
    else:
        bot.send_message(uid, "Выбери из списка ниже:", reply_markup=kb_regions())


def _handle_district(uid, s, text):
    if text == "📍 Весь регион":
        s.filters["district"] = None
        go_main(uid, f"✅ Район: весь регион *{s.filters['region']}*")
        return
    s.filters["district"] = text
    go_main(uid, f"✅ Район: *{text}*")


def _handle_price(uid, s, text):
    if text == "✏️ Ввести вручную":
        s.section = "price_manual"
        s.price_step = "min"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add(
            types.KeyboardButton("◀️ Назад"))
        bot.send_message(uid,
            "Введи *минимальную* сумму в тенге\n(например `500000`, или `0` без ограничения):",
            parse_mode="Markdown", reply_markup=kb)
        return
    # Пресеты
    for label, pmin, pmax in PRICE_PRESETS:
        if text == label:
            s.filters["price_min"] = pmin if pmin > 0 else None
            s.filters["price_max"] = pmax if pmax > 0 else None
            go_main(uid, f"✅ Цена: *{label}*")
            return
    bot.send_message(uid, "Выбери из списка:", reply_markup=kb_price())


def _handle_price_manual(uid, s, text):
    try:
        v = int(text.replace(" ", "").replace("₸", ""))
    except ValueError:
        bot.send_message(uid, "Введи число, например `5000000`:", parse_mode="Markdown")
        return

    if s.price_step == "min":
        s.filters["price_min"] = v if v > 0 else None
        s.price_step = "max"
        bot.send_message(uid,
            f"✅ Мин: *{fmt(v)}*\n\nТеперь введи *максимум* (или `0` без ограничения):",
            parse_mode="Markdown")
    else:
        s.filters["price_max"] = v if v > 0 else None
        s.price_step = None
        go_main(uid, f"✅ Цена: {fmt(s.filters['price_min'])} — {fmt(s.filters['price_max'])}")


def _handle_keyword(uid, s, text):
    s.filters["keyword"] = None if text == "-" else text
    label = text if text != "-" else "убрано"
    go_main(uid, f"✅ Ключевое слово: *{label}*")

# ─────────────────────────────────────────────────────────
#  ПОДПИСКА
# ─────────────────────────────────────────────────────────

def _toggle_subscription(uid: int, s: UserState):
    s.sub_active = not s.sub_active
    db.save_subscription(uid, s.filters, s.sub_active)

    if s.sub_active:
        go_main(uid,
            "🔔 *Подписка включена!*\n\n"
            f"{filters_text(s)}\n\n"
            "Буду присылать уведомления как только появится подходящий тендер."
        )
    else:
        go_main(uid, "🔕 Подписка отключена.")

# ─────────────────────────────────────────────────────────
#  ПОИСК
# ─────────────────────────────────────────────────────────

def _do_search(uid: int, s: UserState):
    # Сначала ищем в локальной БД
    results = db.search_tenders(s.filters)

    if results:
        _send_results(uid, results, s)
        return

    # Если локальная БД пуста — идём в FastAPI
    try:
        resp = httpx.post(
            f"{FASTAPI_URL}/api/tenders/search",
            json={"filters": s.filters},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            # FastAPI возвращает items или results
            items = data.get("items") or data.get("results") or []
            if items:
                _send_results(uid, items, s)
            else:
                _send_demo(uid, s)
        else:
            _send_demo(uid, s)
    except httpx.ConnectError:
        _send_demo(uid, s)


def _send_results(uid: int, tenders: list, s: UserState):
    text = f"📋 *Найдено: {len(tenders)}*\n\n"
    for i, t in enumerate(tenders[:10], 1):
        price = t.get("price") or t.get("amount") or 0
        text += (
            f"*{i}. {t.get('title', 'Без названия')}*\n"
            f"   💰 {price:,.0f} ₸  |  📍 {t.get('region', '')}\n"
            f"   🆔 `{t.get('id', '—')}`\n\n"
        ).replace(",", " ")
    bot.send_message(uid, text, parse_mode="Markdown", reply_markup=kb_main(s))


def _send_demo(uid: int, s: UserState):
    bot.send_message(uid,
        "😕 По вашим фильтрам сейчас ничего не найдено.\n"
        "Попробуйте изменить регион, цену или ключевое слово.",
        reply_markup=kb_main(s)
    )

# ─────────────────────────────────────────────────────────
#  ФОНОВЫЙ ПОТОК — МГНОВЕННЫЕ УВЕДОМЛЕНИЯ
#  Каждые 60 сек проверяем новые тендеры для подписчиков
# ─────────────────────────────────────────────────────────

def notification_worker():
    """Фоновый поток. Проверяет новые тендеры и рассылает уведомления."""
    print("[Notifier] Запущен фоновый поток уведомлений")
    while True:
        try:
            subscriptions = db.get_all_active_subscriptions()
            for sub in subscriptions:
                uid     = sub["user_id"]
                filters = sub["filters"]
                last_id = sub.get("last_notified_id")

                new_tenders = db.get_new_tenders(filters, since_id=last_id)
                if not new_tenders:
                    continue

                for tender in new_tenders:
                    try:
                        price = tender.get("price") or tender.get("amount") or 0
                        bot.send_message(
                            uid,
                            f"🔔 *Новый тендер по вашей подписке!*\n\n"
                            f"*{tender.get('title', 'Без названия')}*\n"
                            f"💰 {price:,.0f} ₸\n"
                            f"📍 {tender.get('region', '—')}\n"
                            f"🆔 `{tender.get('id', '—')}`",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        print(f"[Notifier] Ошибка отправки для {uid}: {e}")

                # Обновляем last_notified_id
                db.update_last_notified(uid, new_tenders[-1]["id"])

        except Exception as e:
            print(f"[Notifier] Ошибка: {e}")

        time.sleep(60)  # проверяем каждую минуту


# ─────────────────────────────────────────────────────────
#  ЗАПУСК
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[Bot] Запущен. MY_ID={MY_ID}")

    try:
        bot.remove_webhook()
    except Exception as e:
        print(f"[Bot] Не удалось удалить webhook: {e}")

    # Запускаем фоновый поток уведомлений
    t = threading.Thread(target=notification_worker, daemon=True)
    t.start()

    bot.infinity_polling(timeout=30, long_polling_timeout=20, skip_pending=True)