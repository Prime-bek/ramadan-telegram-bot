import logging
import json
import os
import asyncio  # Добавлено для задержки
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from threading import Lock  # Добавлено для защиты файла
from telegram.ext import MessageHandler, filters

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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ---------------- DATA ----------------
users_lock = Lock()  # Защита для записи в файл
TIMES_CACHE = {}     # Кэш для расписания

def load_users():
    if os.path.exists("users.json"):
        try:
            with open("users.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except: return {}
    return {}

def save_users():
    # Использование lock для предотвращения повреждения файла
    with users_lock:
        with open("users.json", "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)

users = load_users()

def save_user_data(user_obj, uid):
    # Создаем объект часового пояса Ташкента
    tashkent_tz = ZoneInfo("Asia/Tashkent")
    # Получаем текущее время именно в этом поясе
    now_tashkent = datetime.now(tashkent_tz).strftime("%Y-%m-%d %H:%M:%S")

    if uid not in users:
        users[uid] = {
            "lang": "ru", 
            "city": "tashkent", 
            "remind_min": 10,
            "first_name": user_obj.first_name, 
            "username": user_obj.username,
            "joined": now_tashkent  # Используем время Ташкента
        }
    else:
        users[uid]["first_name"] = user_obj.first_name
        users[uid]["username"] = user_obj.username
    
    # Записываем активность тоже по Ташкенту
    users[uid]["last_active"] = now_tashkent
    save_users()
    
# ---------------- HELPERS ----------------
def t(uid, key):
    lang = users.get(str(uid), {}).get("lang", "ru")
    return TEXTS.get(lang, {}).get(key, key)

def get_city_times(city):
    # Реализация кэширования для ускорения
    if city in TIMES_CACHE:
        return TIMES_CACHE[city]

    file = f"times_{city}.json"
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            TIMES_CACHE[city] = data
            return data
    return {}

def get_tz(uid):
    city = users.get(str(uid), {}).get("city", "tashkent")
    return ZoneInfo("Europe/Berlin" if city == "bremen" else "Asia/Tashkent")

def format_pretty_date(dt, uid):
    """22 февраля 2026 / 22 fevral 2026"""
    lang = users.get(str(uid), {}).get("lang", "ru")
    month = TEXTS[lang]["months"][dt.month - 1]
    return f"{dt.day} {month} {dt.year}"

# ---------------- KEYBOARDS ----------------
def main_kb(uid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(uid, "today"), callback_data="day_today"),
         InlineKeyboardButton(t(uid, "tomorrow"), callback_data="day_tomorrow")],
        [InlineKeyboardButton(t(uid, "countdown"), callback_data="run_countdown")],
        [InlineKeyboardButton(t(uid, "settings"), callback_data="menu_settings")]
    ])

def settings_kb(uid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(uid, "set_lang_btn"), callback_data="set_lang"),
         InlineKeyboardButton(t(uid, "set_city_btn"), callback_data="set_city")],
        [InlineKeyboardButton(t(uid, "set_remind_btn"), callback_data="set_remind")],
        [InlineKeyboardButton(t(uid, "back_btn"), callback_data="back_main")]
    ])
def admin_kb():
    return InlineKeyboardMarkup([
        # Кнопка теперь передает "0" — это начальная страница
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users_0")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")]
    ])
# ---------------- COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    save_user_data(update.effective_user, uid)
    await update.message.reply_text(t(uid, "start"), reply_markup=main_kb(uid))

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = " ".join(context.args)
    if not msg: return
    
    for uid in users.keys():
        try: 
            await context.bot.send_message(chat_id=int(uid), text=f"📢 {msg}")
            await asyncio.sleep(0.05)  # Задержка против блокировок
        except: continue
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
        "🛠 Админ панель",
        reply_markup=admin_kb()
    )
async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    if not context.user_data.get("broadcast_mode"):
        return

    context.user_data["broadcast_mode"] = False

    msg = update.message.text

    sent = 0

    for uid in users.keys():
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"📢 {msg}"
            )
            sent += 1
            await asyncio.sleep(0.05)
        except:
            continue

    await update.message.reply_text(
        f"✅ Рассылка завершена\nОтправлено: {sent}"
    )        

# ---------------- HANDLERS ----------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = str(q.message.chat.id)
    await q.answer()
    save_user_data(update.effective_user, uid)

    tz = get_tz(uid)
    now = datetime.now(tz)
    city = users[uid]["city"]
    times = get_city_times(city)

    if q.data == "run_countdown":
        today = now.strftime("%Y-%m-%d")
        if today not in times:
            await q.edit_message_text("❌ No data", reply_markup=main_kb(uid))
            return
        iftar_dt = datetime.strptime(f"{today} {times[today]['iftar']}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        diff = iftar_dt - now
        
        if diff.total_seconds() <= 0:
            text = "🌙 Iftorlik vaqti bo'ldi!"
        else:
            # Исправленный расчет времени через total_seconds
            total = int(diff.total_seconds())
            h = total // 3600
            m = (total % 3600) // 60
            text = f"{t(uid,'iftar_left')}\n\n⏳ {h} {t(uid,'hour')} {m} {t(uid,'minute')}\n🕰 {times[today]['iftar']}"
        await q.edit_message_text(text, reply_markup=main_kb(uid))

    elif q.data.startswith("day_"):
        target = now if q.data == "day_today" else now + timedelta(days=1)
        ds = target.strftime("%Y-%m-%d")
        if ds in times:
            res = times[ds]
            date_str = format_pretty_date(target, uid)
            text = f"📅 {date_str}\n\n{t(uid,'suhoor_until')} {res['suhoor']}\n{t(uid,'iftar_time')} {res['iftar']}"
        else: text = "❌ No data"
        await q.edit_message_text(text, reply_markup=main_kb(uid))

    elif q.data == "menu_settings":
        await q.edit_message_text(t(uid, "settings_title"), reply_markup=settings_kb(uid))

    elif q.data == "back_main":
        await q.edit_message_text(t(uid, "start"), reply_markup=main_kb(uid))

    elif q.data == "set_lang":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
                                    InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz")]])
        await q.edit_message_text("Выберите язык / Tilni tanlang:", reply_markup=kb)

    elif q.data.startswith("lang_"):
        users[uid]["lang"] = q.data.split("_")[1]
        save_users()
        await q.edit_message_text(t(uid, "lang_changed"), reply_markup=main_kb(uid))

    elif q.data == "set_city":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Tashkent", callback_data="city_tashkent")],
                                    [InlineKeyboardButton("Bremen", callback_data="city_bremen")]])
        await q.edit_message_text(t(uid, "choose_city"), reply_markup=kb)

    elif q.data.startswith("city_"):
        users[uid]["city"] = q.data.split("_")[1]
        save_users()
        await q.edit_message_text(t(uid, "city_changed"), reply_markup=main_kb(uid))

    elif q.data == "set_remind":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("5 min", callback_data="rem_5"),
                                    InlineKeyboardButton("10 min", callback_data="rem_10"),
                                    InlineKeyboardButton("15 min", callback_data="rem_15")]])
        await q.edit_message_text(t(uid, "choose_rem"), reply_markup=kb)

    elif q.data.startswith("rem_"):
        users[uid]["remind_min"] = int(q.data.split("_")[1])
        save_users()
        await q.edit_message_text(t(uid, "remind_changed"), reply_markup=main_kb(uid))

            # ---------------- ADMIN PANEL ----------------

    elif q.data == "admin_users":
        if update.effective_user.id != ADMIN_ID:
            return
        
    

        buttons = []
        for uid, data in list(users.items())[:20]:  # первые 20 пользователей
            name = data.get("first_name", "NoName")
            buttons.append([
                InlineKeyboardButton(
                    f"{name} ({uid})",
                    callback_data=f"admin_user_{uid}"
                )
            ])

        await q.edit_message_text(
            "👥 Пользователи:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    

    # ---------------- АДМИНКА: СПИСОК ПОЛЬЗОВАТЕЛЕЙ (С ПАГИНАЦИЕЙ) ----------------
    elif q.data.startswith("admin_users"):
        if update.effective_user.id != ADMIN_ID: return
        
        # Извлекаем номер страницы из callback (admin_users_0, admin_users_1 и т.д.)
        parts = q.data.split("_")
        page = int(parts[2]) if len(parts) > 2 else 0
        per_page = 15
        
        user_list = list(users.items())
        total = len(user_list)
        
        start_idx = page * per_page
        end_idx = start_idx + per_page
        page_users = user_list[start_idx:end_idx]

        buttons = []
        for u_id, u_data in page_users:
            name = u_data.get("first_name", "User")
            buttons.append([InlineKeyboardButton(f"👤 {name} ({u_id})", callback_data=f"admin_user_{u_id}_{page}")])

        # Кнопки управления страницами
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_users_{page-1}"))
        if end_idx < total:
            nav.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"admin_users_{page+1}"))
        
        if nav: buttons.append(nav)
        buttons.append([InlineKeyboardButton("⬅️ В меню админа", callback_data="admin_back")])

        await q.edit_message_text(
            f"👥 ПОЛЬЗОВАТЕЛИ (Страница {page+1})\nВсего в базе: {total}", 
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    # ---------------- АДМИНКА: ПРОСМОТР КОНКРЕТНОГО ЮЗЕРА ----------------
    elif q.data.startswith("admin_user_"):
        if update.effective_user.id != ADMIN_ID: return

        # Получаем ID и страницу, чтобы вернуться назад на ту же страницу
        data_parts = q.data.split("_")
        target_uid = data_parts[2]
        back_page = data_parts[3] if len(data_parts) > 3 else 0
        
        user = users.get(target_uid)
        if not user:
            await q.edit_message_text("❌ Пользователь не найден", reply_markup=admin_kb())
            return

        info = (
            "👤 ДЕТАЛИ ПОЛЬЗОВАТЕЛЯ\n\n"
            f"🆔 ID: {target_uid}\n"
            f"👤 Имя: {user.get('first_name')}\n"
            f"🔗 Username: @{user.get('username')}\n"
            f"🌐 Язык: {user.get('lang')}\n"
            f"🌍 Город: {user.get('city')}\n"
            f"🔔 Напоминание: {user.get('remind_min')} мин\n"
            f"📅 Зашёл: {user.get('joined')}\n"
            f"⚡ Активен: {user.get('last_active')}"
        )
        
        # Кнопка возврата именно на ту страницу, с которой пришли
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад к списку", callback_data=f"admin_users_{back_page}")]])
        await q.edit_message_text(info, reply_markup=kb)

    # ---------------- АДМИНКА: СТАТИСТИКА ----------------
    elif q.data == "admin_stats":
        if update.effective_user.id != ADMIN_ID: return

        total_users = len(users)
        today_str = datetime.now().strftime("%Y-%m-%d")
        active_today = sum(1 for u in users.values() if u.get("last_active", "").startswith(today_str))

        lang_stats = {}
        city_stats = {}
        for u in users.values():
            l = u.get("lang", "unknown"); lang_stats[l] = lang_stats.get(l, 0) + 1
            c = u.get("city", "unknown"); city_stats[c] = city_stats.get(c, 0) + 1

        text = f"📊 СТАТИСТИКА БОТА\n\n👥 Всего: {total_users}\n🔥 Сегодня активны: {active_today}\n\n🌐 Языки:\n"
        for lang, count in lang_stats.items(): text += f"• {lang}: {count}\n"
        text += "\n🌍 Города:\n"
        for city, count in city_stats.items(): text += f"• {city}: {count}\n"

        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ В меню админа", callback_data="admin_back")]])
        await q.edit_message_text(text, reply_markup=kb)

    # ---------------- АДМИНКА: РАССЫЛКА ----------------
    elif q.data == "admin_broadcast":
        if update.effective_user.id != ADMIN_ID: return
        context.user_data["broadcast_mode"] = True
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin_back")]])
        await q.edit_message_text(
            "📢 РЕЖИМ РАССЫЛКИ\n\nОтправь текст сообщения следующим сообщением, и оно уйдет всем пользователям.",
            reply_markup=kb
        )

    # ---------------- ВОЗВРАТ В МЕНЮ ----------------
    elif q.data == "admin_back":
        if update.effective_user.id == ADMIN_ID:
            await q.edit_message_text("🛠 ГЛАВНОЕ МЕНЮ АДМИНА", reply_markup=admin_kb())
        
# ---------------- SCHEDULER ----------------
async def send_notification(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_message(chat_id=context.job.chat_id, text=context.job.data)
    except Exception as e:
        logging.error(f"Error sending to {context.job.chat_id}: {e}")

async def run_scheduler(context: ContextTypes.DEFAULT_TYPE):
    for job in list(context.job_queue.jobs()):
        if job.name and job.name.startswith("rem_"):
            job.schedule_removal()

    for uid, prefs in users.items():
        tz = get_tz(uid)
        now = datetime.now(tz)
        today = now.strftime("%Y-%m-%d")
        times = get_city_times(prefs["city"])
        if today not in times: continue

        rm = prefs.get("remind_min", 10)
        date_head = format_pretty_date(now, uid)

        for event in ["suhoor", "iftar"]:
            ev_time = times[today][event]
            ev_dt = datetime.strptime(f"{today} {ev_time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
            rem_dt = ev_dt - timedelta(minutes=rm)

            if rem_dt > now:
                dua_title = t(uid, f"{event}_dua_title")
                dua_text = t(uid, f"{event}_dua")
                rem_text = t(uid, f"{event}_rem_text")
                label = t(uid, "close_time" if event == "suhoor" else "open_time")

                msg = (
                    f"📅 {date_head}\n\n"
                    f"⏳ {rem_text} {rm} {t(uid, 'minute')}!\n"
                    f"🕰 {label}: {ev_time}\n\n"
                    f"{dua_title}\n{dua_text}"
                )

                context.job_queue.run_once(
                    send_notification, rem_dt, 
                    chat_id=int(uid), data=msg, 
                    name=f"rem_{uid}_{event}"
                )

# ---------------- MAIN ----------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_message_handler))

    app.job_queue.run_daily(run_scheduler, time=time(0, 5))
    app.job_queue.run_once(run_scheduler, 5)

    print("БОТ ЗАПУЩЕН")
    app.run_polling()

if __name__ == "__main__":
    main()