import logging
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from translations import TEXTS

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
        with open("users.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_users():
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

users = load_users()

# ---------------- DUA ----------------

DUA_SUHOOR = """Navaytu an asuma sovma shahri ramazona minal fajri ilal mag'ribi xolisan lillahi ta'ala. Allohu akbak"""

DUA_IFTAR = """Allohumma laka sumtu va bika amantu va a'layka tavakkaltu va a'la rizqika aftortu, fag'firliy ya G'offaru ma qoddamtu va ma axxortu,"""

IFTAR_REWARD = """✨ Пусть Аллах примет ваш пост 🤲

Посланник Аллаха ﷺ сказал:

"У постящегося две радости:
радость при разговении
и радость при встрече со своим Господом."

📚 Бухари, Муслим"""


# ---------------- FORMAT DATE ----------------

def format_date_ru(date_obj):
    months = {
        1: "января", 2: "февраля", 3: "марта",
        4: "апреля", 5: "мая", 6: "июня",
        7: "июля", 8: "августа", 9: "сентября",
        10: "октября", 11: "ноября", 12: "декабря"
    }

    weekdays = {
        0: "Понедельник", 1: "Вторник", 2: "Среда",
        3: "Четверг", 4: "Пятница", 5: "Суббота",
        6: "Воскресенье"
    }

    return f"{date_obj.day} {months[date_obj.month]} {date_obj.year} ({weekdays[date_obj.weekday()]})"


# ---------------- KEYBOARD ----------------

def main_keyboard(chat_id):
    keyboard = [
        [InlineKeyboardButton(t(chat_id,"today"), callback_data="today")],
        [InlineKeyboardButton(t(chat_id,"tomorrow"), callback_data="tomorrow")],
        [InlineKeyboardButton(t(chat_id,"countdown"), callback_data="countdown")],
        [InlineKeyboardButton(t(chat_id,"check_time"), callback_data="check_time")],
    ]
    return InlineKeyboardMarkup(keyboard)

def language_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz")]
    ])

def t(chat_id, key):
    chat_id = str(chat_id)
    lang = users.get(chat_id, {}).get("lang", "ru")
    return TEXTS[lang][key]


# ---------------- COMMANDS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if chat_id not in users:
        users[chat_id] = {
            "lang": "ru",
            "country": "uz"
        }
        save_users()

    await update.message.reply_text(
        "🌍 Выберите язык / Tilni tanlang:",
        reply_markup=language_keyboard()
    )
    


async def check_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(UZ_TZ)

    await update.message.reply_text(
        f"""🕰 Текущее серверное время

📅 {format_date_ru(now)}
⏰ {now.strftime('%H:%M:%S')}
🌍 Asia/Tashkent"""
    )


# ---------------- BUTTON HANDLER ----------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    now = datetime.now(UZ_TZ)

    # ---------- LANGUAGE SWITCH ----------
    if query.data.startswith("lang_"):
        lang = query.data.split("_")[1]

        chat_id = str(query.message.chat.id)
        users[chat_id]["lang"] = lang
        save_users()

        await query.edit_message_text(
    t(chat_id, "lang_changed"),
    reply_markup=main_keyboard(chat_id)
)
        return    

    # ---------- CHECK TIME ----------
    if query.data == "check_time":
        await query.edit_message_text(
            f"🕰 {format_date_ru(now)}\n⏰ {now.strftime('%H:%M:%S')}",
            reply_markup=main_keyboard(chat_id)
        )
        return

    # ---------- COUNTDOWN ----------
    if query.data == "countdown":
        today = now.strftime("%Y-%m-%d")

        if today not in TIMES:
            await query.edit_message_text("Нет данных на сегодня.")
            return

        iftar_str = TIMES[today]["iftar"]

        iftar_time = datetime.strptime(
            today + " " + iftar_str,
            "%Y-%m-%d %H:%M"
        ).replace(tzinfo=UZ_TZ)

        diff = iftar_time - now

        if diff.total_seconds() <= 0:
            text = "🌙 Ифтар уже наступил!"
        else:
            hours = diff.seconds // 3600
            minutes = (diff.seconds % 3600) // 60

            text = f"""🌙 До ифтара осталось:

⏳ {hours} ч {minutes} мин
🕰 Ифтар в: {iftar_str}
📅 {format_date_ru(now)}"""

        await query.edit_message_text(
            text,
            reply_markup=main_keyboard(chat_id)
        )
        return

    # ---------- TODAY ----------
    if query.data == "today":
        date_obj = now

    elif query.data == "tomorrow":
        date_obj = now + timedelta(days=1)

    else:
        return

    date_str = date_obj.strftime("%Y-%m-%d")

    if date_str in TIMES:
        suhoor = TIMES[date_str]["suhoor"]
        iftar = TIMES[date_str]["iftar"]

        await query.edit_message_text(
            f"""📅 {format_date_ru(date_obj)}

🌅 Сухур до: {suhoor}
🌙 Ифтар в: {iftar}""",
            reply_markup=main_keyboard(chat_id)
        )


# ---------------- DAILY REMINDERS ----------------

async def daily_scheduler(context: ContextTypes.DEFAULT_TYPE):
    today_obj = datetime.now(UZ_TZ)
    today = today_obj.strftime("%Y-%m-%d")

    if today not in TIMES:
        return

    suhoor_time = datetime.strptime(
        today + " " + TIMES[today]["suhoor"],
        "%Y-%m-%d %H:%M"
    ).replace(tzinfo=UZ_TZ)

    iftar_time = datetime.strptime(
        today + " " + TIMES[today]["iftar"],
        "%Y-%m-%d %H:%M"
    ).replace(tzinfo=UZ_TZ)

    for user in users:
        context.job_queue.run_once(reminder_suhoor_10, suhoor_time - timedelta(minutes=10), chat_id=user)
        context.job_queue.run_once(reminder_iftar_10, iftar_time - timedelta(minutes=10), chat_id=user)
        context.job_queue.run_once(iftar_reward, iftar_time + timedelta(minutes=1), chat_id=user,)


async def reminder_suhoor_10(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(UZ_TZ)
    today = now.strftime("%Y-%m-%d")
    suhoor = TIMES[today]["suhoor"]

    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"""📅 {format_date_ru(now)}

⏳ До окончания сухура осталось 10 минут!
🕰 Время закрытия: {suhoor}

📿 Дуа сухура:
{DUA_SUHOOR}"""
    )


async def reminder_iftar_10(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(UZ_TZ)
    today = now.strftime("%Y-%m-%d")
    iftar = TIMES[today]["iftar"]

    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"""📅 {format_date_ru(now)}

⏳ До ифтара осталось 10 минут!
🕰 Время открытия: {iftar}

📿 Дуа ифтара:
{DUA_IFTAR}"""
    )
async def iftar_reward(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=IFTAR_REWARD
    )
    


# ---------------- MAIN ----------------
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users = len(users)

    await update.message.reply_text(
        f"""📊 Статистика бота

👥 Пользователей: {total_users}
🌙 Ramadan Reminder Bot"""
    )
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("checktime", check_time))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("stats", stats))

    app.job_queue.run_daily(
        daily_scheduler,
        time=datetime.strptime("00:05", "%H:%M").time(),
    )

    app.job_queue.run_once(daily_scheduler, 5)

    print("Бот запущен 🚀")
    app.run_polling()


if __name__ == "__main__":
    main()