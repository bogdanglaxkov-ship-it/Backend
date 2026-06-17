import os

import telebot
import httpx
from telebot import types
from dotenv import load_dotenv


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
raw_id = os.getenv("MY_ID")
MY_ID = int(raw_id) if raw_id else None

FASTAPI_URL = os.getenv("FASTAPI_URL",)


# ─────────────────────────────────────────────
#  СЮДА ВСТАВЬ СВОИ ДАННЫЕ
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────

bot = telebot.TeleBot(BOT_TOKEN)

# Простое хранилище фильтров (только для одного пользователя)
filters = {
    "region":    None,
    "district":  None,
    "price_min": None,
    "price_max": None,
    "keyword":   None,
}
step = {"current": "idle"}  # idle | region | district | price | keyword

REGIONS = {
    "Астана":        ["Сарыарка", "Байконыр", "Есиль"],
    "Алматы":        ["Алатауский", "Алмалинский", "Бостандыкский"],
    "Шымкент":       ["Абайский", "Аль-Фарабийский", "Енбекшинский"],
    "Акмолинская":   ["Аккольский", "Атбасарский", "Буландынский"],
    "Актюбинская":   ["Айтекебийский", "Алгинский", "Иргизский"],
    "Атырауская":    ["Атырауский", "Индерский", "Исатайский"],
    "ВКО":           ["Абайский", "Аягозский", "Глубоковский"],
    "Жамбылская":    ["Байзакский", "Жамбылский", "Кордайский"],
    "Карагандинская":["Абайский", "Актогайский", "Каркаралинский"],
    "Костанайская":  ["Алтынсаринский", "Аулиекольский", "Денисовский"],
    "Кызылординская":["Аральский", "Жалагашский", "Казалинский"],
    "Мангистауская": ["Бейнеуский", "Каракиянский", "Мунайлинский"],
    "Павлодарская":  ["Аксуский", "Баянаульский", "Железинский"],
    "СКО":           ["Айыртауский", "Акжарский", "Есильский"],
    "Туркестанская": ["Арысский", "Байдибекский", "Казыгуртский"],
    "ЗКО":           ["Акжаикский", "Бурлинский", "Жангалинский"],
    "Улытауская":    ["Джезказганский", "Сатпаев", "Улытауский"],
}


def only_me(message):
    """Блокирует всех кроме тебя."""
    if message.from_user.id != MY_ID:
        bot.reply_to(message, "Этот бот личный, доступ только для владельца.")
        return False
    return True


def fmt(v):
    if not v:
        return "не указано"
    return f"{v:,} ₸".replace(",", " ")


def show_filters():
    r = filters["region"] or "Все"
    d = filters["district"] or "Весь регион"
    return (
        f"📍 Регион: {r}\n"
        f"📌 Район: {d}\n"
        f"💰 От: {fmt(filters['price_min'])}\n"
        f"💰 До: {fmt(filters['price_max'])}\n"
        f"🔑 Слово: {filters['keyword'] or '—'}"
    )


# ── Главное меню ──────────────────────────────
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton("🔍 Искать"),
        types.KeyboardButton("⚙️ Фильтры"),
        types.KeyboardButton("🗺 Регион"),
        types.KeyboardButton("💰 Цена"),
        types.KeyboardButton("🔄 Сбросить"),
        types.KeyboardButton("ℹ️ Статус"),
    )
    return kb


# ── /start ────────────────────────────────────
@bot.message_handler(commands=["start"])
def cmd_start(message):
    if not only_me(message): return
    bot.send_message(
        message.chat.id,
        "👋 Привет! Это твой личный бот Oylan.\n\n"
        "Настрой фильтры и нажми *«🔍 Искать»*.",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )


# ── Статус текущих фильтров ───────────────────
@bot.message_handler(func=lambda m: m.text == "ℹ️ Статус")
def cmd_status(message):
    if not only_me(message): return
    bot.send_message(message.chat.id,
        f"*Текущие фильтры:*\n\n{show_filters()}",
        parse_mode="Markdown"
    )


# ── Сброс фильтров ────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🔄 Сбросить")
def cmd_reset(message):
    if not only_me(message): return
    for k in filters:
        filters[k] = None
    step["current"] = "idle"
    bot.send_message(message.chat.id, "✅ Фильтры сброшены.", reply_markup=main_menu())


# ── Выбор региона ─────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🗺 Регион")
def cmd_region(message):
    if not only_me(message): return
    step["current"] = "region"
    kb = types.InlineKeyboardMarkup(row_width=2)
    for r in REGIONS:
        kb.add(types.InlineKeyboardButton(r, callback_data=f"r:{r}"))
    kb.add(types.InlineKeyboardButton("🌍 Все регионы", callback_data="r:ALL"))
    bot.send_message(message.chat.id, "📍 Выбери регион:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("r:"))
def cb_region(call):
    val = call.data[2:]
    if val == "ALL":
        filters["region"] = None
        filters["district"] = None
        step["current"] = "idle"
        bot.edit_message_text("✅ Регион: *Все регионы*", call.message.chat.id,
            call.message.message_id, parse_mode="Markdown")
    else:
        filters["region"] = val
        step["current"] = "district"
        kb = types.InlineKeyboardMarkup(row_width=2)
        for d in REGIONS.get(val, []):
            kb.add(types.InlineKeyboardButton(d, callback_data=f"d:{d}"))
        kb.add(types.InlineKeyboardButton("📍 Весь регион", callback_data="d:ALL"))
        bot.edit_message_text(f"📍 Регион: *{val}*\n\nВыбери район:",
            call.message.chat.id, call.message.message_id,
            parse_mode="Markdown", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("d:"))
def cb_district(call):
    val = call.data[2:]
    filters["district"] = None if val == "ALL" else val
    step["current"] = "idle"
    label = val if val != "ALL" else "Весь регион"
    bot.edit_message_text(
        f"✅ Район: *{label}*",
        call.message.chat.id, call.message.message_id, parse_mode="Markdown"
    )


# ── Цена ──────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "💰 Цена")
def cmd_price(message):
    if not only_me(message): return
    kb = types.InlineKeyboardMarkup(row_width=2)
    presets = [
        ("До 1 млн",     "0:1000000"),
        ("1–5 млн",      "1000000:5000000"),
        ("5–20 млн",     "5000000:20000000"),
        ("20–100 млн",   "20000000:100000000"),
        ("Свыше 100 млн","100000000:0"),
        ("✏️ Вручную",   "custom"),
    ]
    for label, data in presets:
        kb.add(types.InlineKeyboardButton(label, callback_data=f"p:{data}"))
    bot.send_message(message.chat.id, "💰 Выбери диапазон цены:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("p:"))
def cb_price(call):
    val = call.data[2:]
    if val == "custom":
        step["current"] = "price_min"
        bot.edit_message_text(
            "Введи минимальную сумму (например *500000*).\nИли *0* без ограничения:",
            call.message.chat.id, call.message.message_id, parse_mode="Markdown"
        )
        return
    pmin, pmax = val.split(":")
    filters["price_min"] = int(pmin) if pmin != "0" else None
    filters["price_max"] = int(pmax) if pmax != "0" else None
    step["current"] = "idle"
    bot.edit_message_text(
        f"✅ Цена: {fmt(filters['price_min'])} — {fmt(filters['price_max'])}",
        call.message.chat.id, call.message.message_id
    )


# ── Ввод цены вручную ─────────────────────────
@bot.message_handler(func=lambda m: step["current"] == "price_min")
def input_price_min(message):
    if not only_me(message): return
    try:
        v = int(message.text.strip().replace(" ", ""))
        filters["price_min"] = v if v > 0 else None
        step["current"] = "price_max"
        bot.send_message(message.chat.id,
            f"✅ Минимум: {fmt(v)}\n\nТеперь введи максимум (или *0*):",
            parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "Введи число, например: *5000000*", parse_mode="Markdown")


@bot.message_handler(func=lambda m: step["current"] == "price_max")
def input_price_max(message):
    if not only_me(message): return
    try:
        v = int(message.text.strip().replace(" ", ""))
        filters["price_max"] = v if v > 0 else None
        step["current"] = "idle"
        bot.send_message(message.chat.id,
            f"✅ Цена задана: {fmt(filters['price_min'])} — {fmt(filters['price_max'])}",
            reply_markup=main_menu())
    except ValueError:
        bot.send_message(message.chat.id, "Введи число, например: *20000000*", parse_mode="Markdown")


# ── Фильтры (просмотр + ввод ключевого слова) ─
@bot.message_handler(func=lambda m: m.text == "⚙️ Фильтры")
def cmd_filters(message):
    if not only_me(message): return
    step["current"] = "keyword"
    bot.send_message(message.chat.id,
        f"*Текущие фильтры:*\n\n{show_filters()}\n\n"
        "Введи ключевое слово для поиска (или напиши *-* чтобы убрать):",
        parse_mode="Markdown"
    )


@bot.message_handler(func=lambda m: step["current"] == "keyword")
def input_keyword(message):
    if not only_me(message): return
    val = message.text.strip()
    filters["keyword"] = None if val == "-" else val
    step["current"] = "idle"
    bot.send_message(message.chat.id,
        f"✅ Ключевое слово: *{filters['keyword'] or 'убрано'}*",
        parse_mode="Markdown", reply_markup=main_menu()
    )


# ── ПОИСК ─────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🔍 Искать")
def cmd_search(message):
    if not only_me(message): return
    bot.send_message(message.chat.id,
        f"⏳ Ищу тендеры...\n\n{show_filters()}")
    do_search(message.chat.id)


def do_search(chat_id):
    payload = {"filters": {k: v for k, v in filters.items()}}
    try:
        resp = httpx.post(f"{FASTAPI_URL}/api/tenders/search", json=payload, timeout=15)
        if resp.status_code == 200:
            tenders = resp.json().get("results", [])
            if not tenders:
                # Если бэкенд вернул пустой список — показываем тестовые данные
                _send_demo(chat_id)
                return
            text = f"📋 *Найдено: {len(tenders)}*\n\n"
            for i, t in enumerate(tenders[:10], 1):
                text += (
                    f"*{i}. Лот №{t.get('lot_number','—')}*\n"
                    f"   {t.get('title','')}\n"
                    f"   💰 {t.get('amount',0):,} ₸\n\n".replace(",", " ")
                )
            bot.send_message(chat_id, text, parse_mode="Markdown")
        else:
            _send_demo(chat_id)
    except httpx.ConnectError:
        # Сервер не запущен — показываем тестовые данные
        _send_demo(chat_id)


def _send_demo(chat_id):
    """Тестовые данные пока FastAPI не запущен."""
    kw = filters["keyword"] or "оборудование"
    r  = filters["region"]  or "Астана"
    bot.send_message(chat_id,
        f"📋 *Тестовые результаты* (FastAPI не запущен)\n\n"
        f"1. *Лот №101* — Поставка {kw}\n"
        f"   📍 {r} | 💰 1 250 000 ₸\n\n"
        f"2. *Лот №102* — Разработка ПО для {kw}\n"
        f"   📍 {r} | 💰 4 500 000 ₸\n\n"
        f"3. *Лот №103* — Услуги по {kw}\n"
        f"   📍 {r} | 💰 890 000 ₸\n\n"
        f"_Подключи FastAPI чтобы получать реальные данные_",
        parse_mode="Markdown", reply_markup=main_menu()
    )


# ── Любой другой текст = быстрый поиск ────────
@bot.message_handler(func=lambda m: step["current"] == "idle")
def fallback(message):
    if not only_me(message): return
    filters["keyword"] = message.text.strip()
    bot.send_message(message.chat.id,
        f"🔍 Ищу: *{message.text}*...", parse_mode="Markdown")
    do_search(message.chat.id)


# ── Запуск ─────────────────────────────────────
if __name__ == "__main__":
    print(f"Бот запущен. Твой ID: {MY_ID}")
    print("Жди сообщений...")
    bot.infinity_polling(timeout=30, long_polling_timeout=20)