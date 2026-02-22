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

# ---------------- DATA MANAGEMENT ----------------
def load_users():
    if os.path.exists("users.json"):
        with open("users.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users():
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

users = load_users()

def save_user_data(user_obj, uid):
    """Сбор всех доступных данных пользователя"""
    if uid not in users:
        users[uid] = {
            "lang": "ru",
            "city": "tashkent",
            "remind_min": 10,
            "first_name": user_obj.first_name,
            "last_name": user_obj.last_name,
            "username": user_obj.username,
            "language_code": user_obj.language_code, # Язык самого приложения TG
            "is_premium": user_obj.is_premium,
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    else:
        # Обновляем данные, если они изменились
        users[uid]["first_name"] = user_obj.first_name
        users[uid]["last_name"] = user_obj.last_name
        users[uid]["username"] = user_obj.username
    
    users[uid]["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_users()

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
        [InlineKeyboardButton(t(uid, "settings"), callback_data="menu_settings")]
    ])

def settings_keyboard(uid):
    # Кнопки в настройках также зависят от выбранного языка
    txt_lang = "🌐 Til / Язык"
    txt_city = "🌍 Shahar / Город"
    txt_rem = "🔔 Eslatma / Уведомление"
    txt_back = "⬅️ Orqaga / Назад"
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(txt_lang, callback_data="set_lang"),
         InlineKeyboardButton(txt_city, callback_data="set_city")],
        [InlineKeyboardButton(txt_rem, callback_data="set_remind")],
        [InlineKeyboardButton(txt_back, callback_data="back_main")]
    ])

# ---------------- COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    save_user_data(update.effective_user, uid)

    await update.message.reply_text(
        t(uid, "start"),
        reply_markup=main_keyboard(uid)
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    total = len(users)
    text = f"📊 *ПОЛНАЯ СТАТИСТИКА*\n\n👥 Всего: {total}\n\n"
    
    for uid, d in list(users.items())[-10:]: # Последние 10
        text += (f"👤 {d.get('first_name')} (@{d.get('username')})\n"
                 f"└ ID: `{uid}` | {d.get('city')} | {d.get('lang')}\n"
                 f"└ Premium: {d.get('is_premium')} | Активен: {d.get('last_active')}\n\n")

    await update.message.reply_text(text[:4000], parse_mode="Markdown")

# ---------------- BUTTON HANDLER ----------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = str(q.message.chat.id)
    save_user_data(update.effective_user, uid)

    tz = get_tz(uid)
    now = datetime.now(tz)
    city = users[uid]["city"]
    times = get_city_times(city)

    # Логика кнопок
    if q.data == "run_countdown":
        today = now.strftime("%Y-%m-%d")
        if today not in times:
            await q.edit_message_text("❌ No data", reply_markup=main_keyboard(uid))
            return
        iftar_str = times[today]["iftar"]
        iftar_dt = datetime.strptime(f"{today} {iftar_str}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        diff = iftar_dt - now
        if diff.total_seconds() <= 0:
            text = "🌙 Ифтар / Iftorlik vaqti bo'ldi!"
        else:
            h, m = diff.seconds // 3600, (diff.seconds % 3600) // 60
            text = f"{t(uid,'iftar_left')}\n\n⏳ {h} {t(uid,'hour')} {m} {t(uid,'minute')}\n🕰 {iftar_str}"
        await q.edit_message_text(text, reply_markup=main_keyboard(uid))

    elif q.data.startswith("day_"):
        target = now if q.data == "day_today" else now + timedelta(days=1)
        ds = target.strftime("%Y-%m-%d")
        if ds in times:
            res = times[ds]
            text = f"📅 {ds}\n\n{t(uid,'suhoor_until')} {res['suhoor']}\n{t(uid,'iftar_time')} {res['iftar']}"
        else: text = "❌ No data"
        await q.edit_message_text(text, reply_markup=main_keyboard(uid))

    elif q.data == "menu_settings":
        await q.edit_message_text("⚙️ Sozlamalar / Настройки:", reply_markup=settings_keyboard(uid))

    elif q.data == "back_main":
        await q.edit_message_text(t(uid, "start"), reply_markup=main_keyboard(uid))

    # Настройки Языка
    elif q.data == "set_lang":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
                                    InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz")]])
        await q.edit_message_text("Tilni tanlang / Выберите язык:", reply_markup=kb)
    elif q.data.startswith("lang_"):
        users[uid]["lang"] = q.data.split("_")[1]
        save_users()
        await q.edit_message_text(t(uid, "lang_changed"), reply_markup=main_keyboard(uid))

    # Настройки Города
    elif q.data == "set_city":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Tashkent", callback_data="city_tashkent")],
                                    [InlineKeyboardButton("Bremen", callback_data="city_bremen")]])
        await q.edit_message_text("Shaharni tanlang / Выберите город:", reply_markup=kb)
    elif q.data.startswith("city_"):
        users[uid]["city"] = q.data.split("_")[1]
        save_users()
        await q.edit_message_text(t(uid, "city_changed"), reply_markup=main_keyboard(uid))

    # Настройки напоминаний
    elif q.data == "set_remind":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("5 min", callback_data="rem_5"),
                                    InlineKeyboardButton("10 min", callback_data="rem_10"),
                                    InlineKeyboardButton("15 min", callback_data="rem_15")]])
        await q.edit_message_text("Eslatma vaqti / Время напоминания:", reply_markup=kb)
    elif q.data.startswith("rem_"):
        users[uid]["remind_min"] = int(q.data.split("_")[1])
        save_users()
        await q.edit_message_text(t(uid, "remind_changed"), reply_markup=main_keyboard(uid))

# ---------------- SCHEDULER ----------------
async def send_msg(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_message(chat_id=context.job.chat_id, text=context.job.data)
    except: pass

async def daily_scheduler(context: ContextTypes.DEFAULT_TYPE):
    for job in list(context.job_queue.jobs()):
        if job.name == "reminder": job.schedule_removal()

    for uid, prefs in users.items():
        tz = get_tz(uid)
        now = datetime.now(tz)
        today = now.strftime("%Y-%m-%d")
        times = get_city_times(prefs["city"])
        if today not in times: continue

        rm = prefs.get("remind_min", 10)
        for event in ["suhoor", "iftar"]:
            ev_time = times[today][event]
            ev_dt = datetime.strptime(f"{today} {ev_time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
            rem_dt = ev_dt - timedelta(minutes=rm)

            if rem_dt > now:
                msg = f"🔔 {t(uid, event + '_rem_text')} {rm} {t(uid, 'minute')}\n🕰 {ev_time}"
                context.job_queue.run_once(send_msg, rem_dt, chat_id=int(uid), data=msg, name="reminder")

# ---------------- MAIN ----------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.job_queue.run_daily(daily_scheduler, time=time(0, 5))
    app.job_queue.run_once(daily_scheduler, 5)
    app.run_polling()

if __name__ == "__main__":
    main()