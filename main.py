import logging
import json
import os
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

# Импорт твоего файла с текстами
try:
    from translations import TEXTS
except ImportError:
    TEXTS = {"ru": {"start": "Ошибка: файл translations.py не найден"}}

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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ---------------- DATA MANAGEMENT ----------------

def load_users():
    if os.path.exists("users.json"):
        try:
            with open("users.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_users():
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

users = load_users()

def get_city_times(city):
    filename = f"times_{city}.json"
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def get_tz(uid):
    city = users.get(str(uid), {}).get("city", "tashkent")
    return ZoneInfo("Asia/Tashkent" if city == "tashkent" else "Europe/Berlin")

# ---------------- HELPERS ----------------

def t(chat_id, key):
    uid = str(chat_id)
    lang = users.get(uid, {}).get("lang", "ru")
    return TEXTS.get(lang, {}).get(key, key)

def format_date(date_obj, chat_id):
    lang = users.get(str(chat_id), {}).get("lang", "ru")
    months = {
        "ru": ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"],
        "uz": ["yanvar","fevral","mart","aprel","may","iyun","iyul","avgust","sentyabr","oktyabr","noyabr","dekabr"]
    }
    weekdays = {
        "ru": ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"],
        "uz": ["Dushanba","Seshanba","Chorshanba","Payshanba","Juma","Shanba","Yakshanba"]
    }
    m = months[lang][date_obj.month - 1]
    w = weekdays[lang][date_obj.weekday()]
    return f"{date_obj.day} {m} {date_obj.year} ({w})"

# ---------------- KEYBOARDS ----------------

def main_keyboard(chat_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(chat_id, "today"), callback_data="day_today"),
         InlineKeyboardButton(t(chat_id, "tomorrow"), callback_data="day_tomorrow")],
        [InlineKeyboardButton(t(chat_id, "countdown"), callback_data="day_countdown")],
        [InlineKeyboardButton("⚙️ Настройки / Sozlamalar", callback_data="menu_settings")]
    ])

def settings_keyboard(chat_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌍 Город / Shahar", callback_data="menu_city")],
        [InlineKeyboardButton("🌐 Язык / Til", callback_data="menu_lang")],
        [InlineKeyboardButton("🔔 Напоминание / Eslatma", callback_data="menu_remind")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]
    ])

# ---------------- HANDLERS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    if uid not in users:
        users[uid] = {"lang": "ru", "city": "tashkent", "remind_min": 10}
        save_users()
    await update.message.reply_text(t(uid, "start"), reply_markup=main_keyboard(uid))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(query.message.chat.id)
    data = query.data
    await query.answer()

    tz = get_tz(uid)
    now = datetime.now(tz)

    # --- Навигация ---
    if data == "menu_settings":
        await query.edit_message_text("⚙️ Настройки:", reply_markup=settings_keyboard(uid))
        return
    elif data == "back_main":
        await query.edit_message_text(t(uid, "start"), reply_markup=main_keyboard(uid))
        return

    # --- Язык ---
    elif data == "menu_lang":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🇷🇺 RU", callback_data="setl_ru"), 
                                    InlineKeyboardButton("🇺🇿 UZ", callback_data="setl_uz")]])
        await query.edit_message_text("Выберите язык:", reply_markup=kb)
    elif data.startswith("setl_"):
        users[uid]["lang"] = data.split("_")[1]
        save_users()
        await query.edit_message_text(t(uid, "lang_changed"), reply_markup=main_keyboard(uid))

    # --- Город ---
    elif data == "menu_city":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Tashkent", callback_data="setc_tashkent")],
                                    [InlineKeyboardButton("Bremen", callback_data="setc_bremen")]])
        await query.edit_message_text("Выберите город:", reply_markup=kb)
    elif data.startswith("setc_"):
        users[uid]["city"] = data.split("_")[1]
        save_users()
        await query.edit_message_text("✅ Город изменен", reply_markup=main_keyboard(uid))

    # --- Время напоминания ---
    elif data == "menu_remind":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("5 мин", callback_data="setr_5"),
                                    InlineKeyboardButton("10 мин", callback_data="setr_10"),
                                    InlineKeyboardButton("15 мин", callback_data="setr_15")]])
        await query.edit_message_text("За сколько минут напоминать?", reply_markup=kb)
    elif data.startswith("setr_"):
        users[uid]["remind_min"] = int(data.split("_")[1])
        save_users()
        await query.edit_message_text(f"✅ Время изменено: {users[uid]['remind_min']} мин", reply_markup=main_keyboard(uid))

    # --- Данные (Сегодня/Завтра) ---
    elif data.startswith("day_"):
        action = data.split("_")[1]
        date_obj = now if action == "today" else now + timedelta(days=1)
        date_str = date_obj.strftime("%Y-%m-%d")
        
        times = get_city_times(users[uid]["city"])
        
        if date_str in times:
            res = times[date_str]
            text = f"📅 {format_date(date_obj, uid)}\n\n"
            text += f"{t(uid,'suhoor_until')} {res['suhoor']}\n"
            text += f"{t(uid,'iftar_time')} {res['iftar']}"
            await query.edit_message_text(text, reply_markup=main_keyboard(uid))
        else:
            await query.edit_message_text("❌ Данные не найдены", reply_markup=main_keyboard(uid))

# ---------------- SCHEDULER ----------------

async def send_reminder_msg(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=context.job.chat_id, text=context.job.data)

async def daily_scheduler(context: ContextTypes.DEFAULT_TYPE):
    for uid, prefs in users.items():
        tz = get_tz(uid)
        today = datetime.now(tz).strftime("%Y-%m-%d")
        times = get_city_times(prefs.get("city", "tashkent"))
        
        if today in times:
            rm = prefs.get("remind_min", 10)
            for event in ["suhoor", "iftar"]:
                event_dt = datetime.strptime(f"{today} {times[event]}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
                rem_dt = event_dt - timedelta(minutes=rm)
                
                if rem_dt > datetime.now(tz):
                    msg = f"🔔 {t(uid, event + '_rem_text')}\n🕰 {times[event]}"
                    context.job_queue.run_once(send_reminder_msg, rem_dt, chat_id=int(uid), data=msg)

# ---------------- MAIN ----------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Планировщик: запускается в 00:05 каждый день
    app.job_queue.run_daily(daily_scheduler, time=time(0, 5))
    # Запуск при старте для проверки
    app.job_queue.run_once(daily_scheduler, 2)

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()