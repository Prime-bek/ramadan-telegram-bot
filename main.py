
import logging
import json
from datetime import datetime, timedelta
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
UZ_TZ = ZoneInfo("Asia/Tashkent")

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

import os
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

# ---------- ЗАГРУЗКА РАСПИСАНИЯ ----------
with open("times.json", "r", encoding="utf-8") as f:
    TIMES = json.load(f)


# ---------- ПОЛЬЗОВАТЕЛИ ----------
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


# ---------- ДУА ----------
DUA_SUHOOR = """🌅 Дуа сухура:

Navaytu an asuma sovma shahri ramazona minal fajri ilal mag'ribi xolisan lillahi ta'ala. Allohu akbak
"""

DUA_IFTAR = """🌙 Дуа ифтара:

Allohumma laka sumtu va bika amantu va a'layka tavakkaltu va a'la rizqika aftortu, fag'firliy ya G'offaru ma qoddamtu va ma axxortu,
"""


# ---------- КНОПКИ ----------
def main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data="today")],
        [InlineKeyboardButton("📆 Завтра", callback_data="tomorrow")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ---------- /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    users.add(chat_id)
    save_users(users)

    await update.message.reply_text(
        "Ассаляму алейкум 🌙\n\n"
        "Вы подключены к напоминаниям.\n"
        "Бот будет автоматически отправлять сообщения каждый день 🤲\n\n"
        "Выберите дату для просмотра:",
        reply_markup=main_keyboard()
    )


# ---------- ОБРАБОТКА КНОПОК ----------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    today = datetime.now(UZ_TZ)

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


# ---------- ЕЖЕДНЕВНОЕ ПЛАНИРОВАНИЕ ----------
async def daily_scheduler(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(UZ_TZ).strftime("%Y-%m-%d")

    if today not in TIMES:
        return

    suhoor_str = TIMES[today]["suhoor"]
    iftar_str = TIMES[today]["iftar"]

    suhoor_time = datetime.strptime(today + " " + suhoor_str, "%Y-%m-%d %H:%M")
    iftar_time = datetime.strptime(today + " " + iftar_str, "%Y-%m-%d %H:%M")

    for user in users:

        context.job_queue.run_once(
            reminder_suhoor_10,
            suhoor_time - timedelta(minutes=10),
            chat_id=user,
        )

        context.job_queue.run_once(
            suhoor_exact,
            suhoor_time,
            chat_id=user,
        )

        context.job_queue.run_once(
            reminder_iftar_10,
            iftar_time - timedelta(minutes=10),
            chat_id=user,
        )

        context.job_queue.run_once(
            iftar_exact,
            iftar_time,
            chat_id=user,
        )


# ---------- СООБЩЕНИЯ ----------
async def reminder_suhoor_10(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(UZ_TZ).strftime("%Y-%m-%d")
    suhoor = TIMES[today]["suhoor"]

    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"""📅 Сегодня: {today}

⏳ До окончания сухура осталось 10 минут!
🕰 Время закрытия: {suhoor}

{DUA_SUHOOR}"""
    )


async def suhoor_exact(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime("%Y-%m-%d")
    suhoor = TIMES[today]["suhoor"]

    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"""📅 Сегодня: {today}

🌅 Время сухура закончилось ({suhoor})

Пусть Аллах примет твой пост 🤍"""
    )


async def reminder_iftar_10(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(UZ_TZ).strftime("%Y-%m-%d")
    iftar = TIMES[today]["iftar"]

    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"""📅 Сегодня: {today}

⏳ До ифтара осталось 10 минут!
🕰 Время открытия: {iftar}

{DUA_IFTAR}"""
    )


async def iftar_exact(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(UZ_TZ).strftime("%Y-%m-%d")
    iftar = TIMES[today]["iftar"]

    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"""📅 Сегодня: {today}

🌙 Время ифтара ({iftar})

{DUA_IFTAR}"""
    )


# ---------- ЗАПУСК ----------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Каждый день в 00:05 создаём задачи
    app.job_queue.run_daily(
        daily_scheduler,
        time=datetime.strptime("00:05", "%H:%M").time()
    )

    print("Бот запущен 🚀")
    app.run_polling()


if __name__ == "__main__":
    main()
import logging
import json
from datetime import datetime, timedelta

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

import os
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

# ---------- ЗАГРУЗКА РАСПИСАНИЯ ----------
with open("times.json", "r", encoding="utf-8") as f:
    TIMES = json.load(f)


# ---------- ПОЛЬЗОВАТЕЛИ ----------
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


# ---------- ДУА ----------
DUA_SUHOOR = """🌅 Дуа сухура:

Navaytu an asuma sovma shahri ramazona minal fajri ilal mag'ribi xolisan lillahi ta'ala. Allohu akbak
"""

DUA_IFTAR = """🌙 Дуа ифтара:

Allohumma laka sumtu va bika amantu va a'layka tavakkaltu va a'la rizqika aftortu, fag'firliy ya G'offaru ma qoddamtu va ma axxortu,
"""


# ---------- КНОПКИ ----------
def main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data="today")],
        [InlineKeyboardButton("📆 Завтра", callback_data="tomorrow")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ---------- /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    users.add(chat_id)
    save_users(users)

    await update.message.reply_text(
        "Ассаляму алейкум 🌙\n\n"
        "Вы подключены к напоминаниям.\n"
        "Бот будет автоматически отправлять сообщения каждый день 🤲\n\n"
        "Выберите дату для просмотра:",
        reply_markup=main_keyboard()
    )


# ---------- ОБРАБОТКА КНОПОК ----------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    today = datetime.now(UZ_TZ)

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


# ---------- ЕЖЕДНЕВНОЕ ПЛАНИРОВАНИЕ ----------
async def daily_scheduler(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime("%Y-%m-%d")

    if today not in TIMES:
        return

    suhoor_str = TIMES[today]["suhoor"]
    iftar_str = TIMES[today]["iftar"]

    suhoor_time = datetime.strptime(today + " " + suhoor_str, "%Y-%m-%d %H:%M")
    iftar_time = datetime.strptime(today + " " + iftar_str, "%Y-%m-%d %H:%M")

    for user in users:

        context.job_queue.run_once(
            reminder_suhoor_10,
            suhoor_time - timedelta(minutes=10),
            chat_id=user,
        )

        context.job_queue.run_once(
            suhoor_exact,
            suhoor_time,
            chat_id=user,
        )

        context.job_queue.run_once(
            reminder_iftar_10,
            iftar_time - timedelta(minutes=10),
            chat_id=user,
        )

        context.job_queue.run_once(
            iftar_exact,
            iftar_time,
            chat_id=user,
        )


# ---------- СООБЩЕНИЯ ----------
async def reminder_suhoor_10(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(UZ_TZ).strftime("%Y-%m-%d")
    suhoor = TIMES[today]["suhoor"]

    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"""📅 Сегодня: {today}

⏳ До окончания сухура осталось 10 минут!
🕰 Время закрытия: {suhoor}

{DUA_SUHOOR}"""
    )


async def suhoor_exact(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(UZ_TZ).strftime("%Y-%m-%d")
    suhoor = TIMES[today]["suhoor"]

    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"""📅 Сегодня: {today}

🌅 Время сухура закончилось ({suhoor})

Пусть Аллах примет твой пост 🤍"""
    )


async def reminder_iftar_10(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(UZ_TZ).strftime("%Y-%m-%d")
    iftar = TIMES[today]["iftar"]

    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"""📅 Сегодня: {today}

⏳ До ифтара осталось 10 минут!
🕰 Время открытия: {iftar}

{DUA_IFTAR}"""
    )


async def iftar_exact(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime("%Y-%m-%d")
    iftar = TIMES[today]["iftar"]

    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"""📅 Сегодня: {today}

🌙 Время ифтара ({iftar})

{DUA_IFTAR}"""
    )


# ---------- ЗАПУСК ----------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Каждый день в 00:05 создаём задачи
    app.job_queue.run_daily(
        daily_scheduler,
        time=datetime.strptime("00:05", "%H:%M").time()
    )

    print("Бот запущен 🚀")
    app.run_polling()
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(UZ_TZ)

    await update.message.reply_text(
        f"Серверное время: {now}\n"
        f"Дата: {now.strftime('%Y-%m-%d')}\n"
        f"Время: {now.strftime('%H:%M:%S')}"
    )
    


if __name__ == "__main__":

    main()