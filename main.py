import logging
import json
import os
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from translations import TEXTS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ---------------- CONFIG ----------------
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1265652628

logging.basicConfig(level=logging.INFO)

# ---------------- USERS ----------------
def load_users():
    if os.path.exists("users.json"):
        with open("users.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users():
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

users = load_users()

# ---------------- HELPERS ----------------
def t(uid, key):
    lang = users.get(str(uid), {}).get("lang", "ru")
    return TEXTS.get(lang, {}).get(key, key)

def get_city_times(city):
    file = f"times_{city}.json"
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def get_tz(uid):
    city = users.get(str(uid), {}).get("city", "tashkent")
    return ZoneInfo("Europe/Berlin" if city == "bremen" else "Asia/Tashkent")

# ---------------- KEYBOARDS ----------------
def main_keyboard(uid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(uid, "today"), callback_data="day_today"),
         InlineKeyboardButton(t(uid, "tomorrow"), callback_data="day_tomorrow")],
        [InlineKeyboardButton(t(uid, "countdown"), callback_data="run_countdown")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="menu_settings")]
    ])

def settings_keyboard(uid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Язык", callback_data="set_lang"),
         InlineKeyboardButton("🌍 Город", callback_data="set_city")],
        [InlineKeyboardButton("🔔 Время уведомления", callback_data="set_remind")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]
    ])

# ---------------- COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(update.effective_chat.id)

    if uid not in users:
        users[uid] = {
            "lang": "ru",
            "city": "tashkent",
            "remind_min": 10,
            "username": user.username,
            "name": user.first_name,
            "joined": datetime.utcnow().isoformat()
        }

    users[uid]["last_seen"] = datetime.utcnow().isoformat()
    save_users()

    await update.message.reply_text(
        t(uid, "start"),
        reply_markup=main_keyboard(uid)
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    total = len(users)
    text = f"📊 *BOT STATS*\n\n👥 Всего пользователей: {total}\n\n"
    
    # Список последних 15 пользователей для компактности
    for uid, data in list(users.items())[-15:]:
        text += f"👤 {data.get('name')} (@{data.get('username')}) | {data.get('city')} | {data.get('lang')}\n"

    await update.message.reply_text(text[:4000], parse_mode="Markdown")

# ---------------- BUTTON HANDLER ----------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = str(q.message.chat.id)
    tz = get_tz(uid)
    now = datetime.now(tz)

    users[uid]["last_seen"] = datetime.utcnow().isoformat()
    save_users()

    city = users[uid]["city"]
    times = get_city_times(city)

    # 1. ОБРАТНЫЙ ОТСЧЕТ
    if q.data == "run_countdown":
        today = now.strftime("%Y-%m-%d")
        if today not in times:
            await q.edit_message_text("❌ Нет данных", reply_markup=main_keyboard(uid))
            return

        iftar_str = times[today]["iftar"]
        iftar_dt = datetime.strptime(f"{today} {iftar_str}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        diff = iftar_dt - now

        if diff.total_seconds() <= 0:
            text = "🌙 Ифтар уже наступил!"
        else:
            h, m = diff.seconds // 3600, (diff.seconds % 3600) // 60
            text = f"{t(uid,'iftar_left')}\n\n⏳ {h} {t(uid,'hour')} {m} {t(uid,'minute')}\n🕰 {iftar_str}"
        await q.edit_message_text(text, reply_markup=main_keyboard(uid))

    # 2. СЕГОДНЯ / ЗАВТРА
    elif q.data.startswith("day_"):
        target_date = now if q.data == "day_today" else now + timedelta(days=1)
        ds = target_date.strftime("%Y-%m-%d")
        if ds in times:
            res = times[ds]
            text = f"📅 {ds}\n\n{t(uid,'suhoor_until')} {res['suhoor']}\n{t(uid,'iftar_time')} {res['iftar']}"
        else:
            text = "❌ Нет данных"
        await q.edit_message_text(text, reply_markup=main_keyboard(uid))

    # 3. МЕНЮ НАСТРОЕК
    elif q.data == "menu_settings":
        await q.edit_message_text("⚙️ Настройки:", reply_markup=settings_keyboard(uid))

    elif q.data == "back_main":
        await q.edit_message_text(t(uid, "start"), reply_markup=main_keyboard(uid))

    # 4. ВЫБОР ЯЗЫКА
    elif q.data == "set_lang":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🇷🇺 RU", callback_data="lang_ru"),
                                    InlineKeyboardButton("🇺🇿 UZ", callback_data="lang_uz")]])
        await q.edit_message_text("Выберите язык:", reply_markup=kb)
    elif q.data.startswith("lang_"):
        users[uid]["lang"] = q.data.split("_")[1]
        save_users()
        await q.edit_message_text("✅ Город сохранен", reply_markup=main_keyboard(uid))

    # 5. ВЫБОР ГОРОДА
    elif q.data == "set_city":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Tashkent", callback_data="city_tashkent")],
                                    [InlineKeyboardButton("Bremen", callback_data="city_bremen")]])
        await q.edit_message_text("Выберите город:", reply_markup=kb)
    elif q.data.startswith("city_"):
        users[uid]["city"] = q.data.split("_")[1]
        save_users()
        await q.edit_message_text("✅ Город сохранен", reply_markup=main_keyboard(uid))

    # 6. ВЫБОР ВРЕМЕНИ НАПОМИНАНИЯ
    elif q.data == "set_remind":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("5 мин", callback_data="rem_5"),
                                    InlineKeyboardButton("10 мин", callback_data="rem_10"),
                                    InlineKeyboardButton("15 мин", callback_data="rem_15")]])
        await q.edit_message_text("За сколько минут напоминать?", reply_markup=kb)
    elif q.data.startswith("rem_"):
        users[uid]["remind_min"] = int(q.data.split("_")[1])
        save_users()
        await q.edit_message_text(f"✅ Установлено: {users[uid]['remind_min']} мин", reply_markup=main_keyboard(uid))

# ---------------- REMINDERS ----------------
async def send_msg(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=context.job.chat_id, text=context.job.data)

async def daily_scheduler(context: ContextTypes.DEFAULT_TYPE):
    for job in list(context.job_queue.jobs()):
        if job.name == "reminder":
            job.schedule_removal()

    for uid, prefs in users.items():
        tz = get_tz(uid)
        now = datetime.now(tz)
        today = now.strftime("%Y-%m-%d")
        times = get_city_times(prefs["city"])
        if today not in times: continue

        rm = prefs.get("remind_min", 10)
        for event in ["suhoor", "iftar"]:
            event_time = times[today][event]
            event_dt = datetime.strptime(f"{today} {event_time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
            remind_dt = event_dt - timedelta(minutes=rm)

            if remind_dt > now:
                msg = f"🔔 {t(uid, event + '_rem_text')}\n🕰 {event_time}"
                context.job_queue.run_once(send_msg, remind_dt, chat_id=int(uid), data=msg, name="reminder")

# ---------------- MAIN ----------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.job_queue.run_daily(daily_scheduler, time=time(0, 5))
    app.job_queue.run_once(daily_scheduler, 3)

    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()