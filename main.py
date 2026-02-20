import logging
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ---------------- CONFIG ----------------

TOKEN = os.getenv("BOT_TOKEN")
UZ_TZ = ZoneInfo("Asia/Tashkent")

logging.basicConfig(level=logging.INFO)

# ---------------- LOAD DATA ----------------

with open("times.json", "r", encoding="utf-8") as f:
    TIMES = json.load(f)


def load_users():
    try:
        with open("users.json", "r") as f:
            return set(json.load(f))
    except:
        return set()


def save_users(users):
    with open("users.json", "w") as f:
        json.dump(list(users), f)


users = load_users()

# ---------------- DUA ----------------

DUA_SUHOOR = """🌅 Дуа сухура:

Navaytu an asuma sovma shahri ramazona minal fajri ilal mag'ribi xolisan lillahi ta'ala. Allohu akbak
"""

DUA_IFTAR = """🌙 Дуа ифтара:

Allohumma laka sumtu va bika amantu va a'layka tavakkaltu va a'la rizqika aftortu, fag'firliy ya G'offaru ma qoddamtu va ma axxortu,
"""

# ---------------- KEYBOARD ----------------

def main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data="today")],
        [InlineKeyboardButton("📆 Завтра", callback_data="tomorrow")],
        [InlineKeyboardButton("🕰 Проверить время", callback_data="check_time")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ---------------- COMMANDS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    users.add(chat_id)
    save_users(users)

    await update.message.reply_text(
        "Ассаляму алейкум 🌙\n\n"
        "Вы подключены к напоминаниям.\n\n"
        "Выберите дату:",
        reply_markup=main_keyboard()
    )


async def check_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(UZ_TZ)

    await update.message.reply_text(
        f"""🕰 Текущее серверное время

Дата: {now.strftime('%Y-%m-%d')}
Время: {now.strftime('%H:%M:%S')}
Часовой пояс: Asia/Tashkent"""
    )

# ---------------- BUTTON HANDLER ----------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    today = datetime.now(UZ_TZ)

    if query.data == "check_time":
        now = datetime.now(UZ_TZ)
        await query.edit_message_text(
            f"""🕰 Текущее серверное время

Дата: {now.strftime('%Y-%m-%d')}
Время: {now.strftime('%H:%M:%S')}
Timezone: Asia/Tashkent""",
            reply_markup=main_keyboard()
        )
        return

    if query.data == "today":
        date_obj = today
    elif query.data == "tomorrow":
        date_obj = today + timedelta(days=1)
    else:
        return

    date_str = date_obj.strftime("%Y-%m-%d")
    weekday = date_obj.strftime("%A")

    if date_str in TIMES:
        suhoor = TIMES[date_str]["suhoor"]
        iftar = TIMES[date_str]["iftar"]

        await query.edit_message_text(
            f"""📅 Дата: {date_str}
📆 День: {weekday}

🌅 Сухур до: {suhoor}
🌙 Ифтар в: {iftar}""",
            reply_markup=main_keyboard()
        )
    else:
        await query.edit_message_text(
            "Нет данных на эту дату.",
            reply_markup=main_keyboard()
        )

# ---------------- MAIN ----------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("checktime", check_time))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Бот запущен 🚀")
    app.run_polling()


if __name__ == "__main__":
    main()