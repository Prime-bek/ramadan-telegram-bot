import logging
import json
import os
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from threading import Lock

from telegram import BotCommand, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from translations import TEXTS

# ---------------- CONFIG ----------------
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1265652628

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ---------------- CONSTANTS ----------------
ONBOARD_LANG = "onb_lang"
ONBOARD_CITY = "onb_city"
BROADCAST_MODE = "broadcast_mode"

# ---------------- PATHS ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Railway Volume directory (persistent storage)
DATA_DIR = os.getenv("DATA_DIR", "/data")
os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")

# ---------------- DATA ----------------
users_lock = Lock()
TIMES_CACHE = {}

def load_users():
    """Загружает пользователей из файла с обработкой ошибок"""
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return {}

    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except (json.JSONDecodeError, IOError) as e:
        logging.error(f"Ошибка загрузки users.json: {e}")
        if os.path.exists(USERS_FILE):
            backup_name = f"{USERS_FILE}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            try:
                os.rename(USERS_FILE, backup_name)
                logging.info(f"Создан бэкап: {backup_name}")
            except OSError:
                pass
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return {}

def save_users():
    """Сохраняет пользователей в файл с блокировкой"""
    with users_lock:
        temp_file = f"{USERS_FILE}.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(users, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, USERS_FILE)
        except Exception as e:
            logging.error(f"Ошибка сохранения users.json: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)

# Загружаем пользователей при старте
users = load_users()

def get_user(uid: str):
    """Возвращает данные пользователя или None"""
    return users.get(str(uid))

def update_user(uid: str, **kwargs):
    """Обновляет поля пользователя"""
    uid = str(uid)
    if uid not in users:
        logging.warning(f"Попытка обновить несуществующего пользователя: {uid}")
        return False
    
    users[uid].update(kwargs)
    save_users()
    return True

def update_activity(user_obj, uid):
    """Обновляет время последней активности"""
    uid = str(uid)
    if uid not in users:
        return
    
    tashkent_tz = ZoneInfo("Asia/Tashkent")
    now = datetime.now(tashkent_tz).strftime("%Y-%m-%d %H:%M:%S")
    
    users[uid].update({
        "first_name": user_obj.first_name,
        "username": user_obj.username,
        "last_active": now
    })
    save_users()

def save_user_data(user_obj, uid):
    """Создает или обновляет пользователя"""
    uid = str(uid)
    tashkent_tz = ZoneInfo("Asia/Tashkent")
    now = datetime.now(tashkent_tz).strftime("%Y-%m-%d %H:%M:%S")
    
    if uid not in users:
        users[uid] = {
            "lang": "uz",
            "city": "tashkent",
            "remind_min": 10,
            "first_name": user_obj.first_name,
            "username": user_obj.username,
            "joined": now,
            "last_active": now,
            "push_sent": False
        }
    else:
        users[uid].update({
            "first_name": user_obj.first_name,
            "username": user_obj.username,
            "last_active": now
        })
    
    save_users()

# ---------------- HELPERS ----------------
def t(uid, key):
    """Получает перевод с fallback"""
    uid = str(uid)
    lang = users.get(uid, {}).get("lang", "uz")
    
    text = TEXTS.get(lang, TEXTS["uz"]).get(key)
    if text is None:
        text = TEXTS["uz"].get(key, TEXTS["ru"].get(key, key))
    return text

def get_city_times(city):
    """Получает расписание города с кэшированием"""
    if city in TIMES_CACHE:
        return TIMES_CACHE[city]
    
    file = os.path.join(BASE_DIR, f"times_{city}.json")
    if os.path.exists(file):
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                TIMES_CACHE[city] = data
                return data
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Ошибка загрузки {file}: {e}")
    return {}

def get_tz(uid):
    """Получает часовой пояс пользователя"""
    uid = str(uid)
    city = users.get(uid, {}).get("city", "tashkent")
    return ZoneInfo("Europe/Berlin" if city == "bremen" else "Asia/Tashkent")

def format_pretty_date(dt, uid):
    """Форматирует дату красиво"""
    uid = str(uid)
    lang = users.get(uid, {}).get("lang", "uz")
    months = TEXTS.get(lang, TEXTS["uz"])["months"]
    month = months[dt.month - 1]
    return f"{dt.day} {month} {dt.year}"

# ---------------- KEYBOARDS ----------------
def main_kb(uid):
    """Главная клавиатура"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(uid, "today"), callback_data="day_today"),
            InlineKeyboardButton(t(uid, "tomorrow"), callback_data="day_tomorrow")
        ],
        [InlineKeyboardButton(t(uid, "countdown"), callback_data="run_countdown")],
        [InlineKeyboardButton(t(uid, "settings"), callback_data="menu_settings")]
    ])

def settings_kb(uid):
    """Клавиатура настроек"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(uid, "set_lang_btn"), callback_data="set_lang"),
            InlineKeyboardButton(t(uid, "set_city_btn"), callback_data="set_city")
        ],
        [InlineKeyboardButton(t(uid, "set_remind_btn"), callback_data="set_remind")],
        [InlineKeyboardButton(t(uid, "back_btn"), callback_data="back_main")]
    ])

def admin_kb():
    """Админская клавиатура"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users_0")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")]
    ])

def cancel_broadcast_kb():
    """Клавиатура отмены рассылки"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отменить рассылку", callback_data="cancel_broadcast")]
    ])

# ---------------- COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    uid = str(update.effective_chat.id)
    user_obj = update.effective_user
    
    # Существующий пользователь - обновляем активность
    if uid in users:
        update_activity(user_obj, uid)
        await update.message.reply_text(
            t(uid, "start"),
            reply_markup=main_kb(uid)
        )
        return
    
    # Проверяем, не идет ли уже onboarding
    if context.user_data.get("onboarding"):
        await update.message.reply_text(t(uid, "onboarding_in_progress"))
        return
    
    # Новый пользователь - начинаем onboarding
    context.user_data["onboarding"] = ONBOARD_LANG
    
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="onb_lang_uz"),
            InlineKeyboardButton("🇷🇺 Русский", callback_data="onb_lang_ru"),
        ]
    ])
    
    await update.message.reply_text(
        "Tilni tanlang / Выберите язык:",
        reply_markup=kb
    )

async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /today"""
    uid = str(update.effective_chat.id)
    
    # Регистрируем или обновляем пользователя
    if uid not in users:
        save_user_data(update.effective_user, uid)
    else:
        update_activity(update.effective_user, uid)
    
    tz = get_tz(uid)
    now = datetime.now(tz)
    city = users[uid]["city"]
    times = get_city_times(city)
    today = now.strftime("%Y-%m-%d")
    
    if today not in times:
        await update.message.reply_text(t(uid, "no_data"))
        return
    
    res = times[today]
    date_str = format_pretty_date(now, uid)
    
    text = (
        f"📅 {date_str}\n\n"
        f"{t(uid, 'suhoor_until')} {res['suhoor']}\n"
        f"{t(uid, 'iftar_time')} {res['iftar']}"
    )
    
    await update.message.reply_text(text, reply_markup=main_kb(uid))

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /settings"""
    uid = str(update.effective_chat.id)
    
    # Регистрируем или обновляем пользователя
    if uid not in users:
        save_user_data(update.effective_user, uid)
    else:
        update_activity(update.effective_user, uid)
    
    await update.message.reply_text(
        t(uid, "settings_title"),
        reply_markup=settings_kb(uid)
    )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /broadcast (только для админа)"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    # Проверяем, не в режиме ли уже рассылка
    if context.user_data.get(BROADCAST_MODE):
        await update.message.reply_text(
            "❌ Вы уже в режиме рассылки. Отправьте сообщение или нажмите «Отменить».",
            reply_markup=cancel_broadcast_kb()
        )
        return
    
    # Проверяем аргументы
    msg = " ".join(context.args)
    
    if not msg:
        # Нет аргументов - входим в интерактивный режим с кнопкой отмены
        context.user_data[BROADCAST_MODE] = True
        await update.message.reply_text(
            "📢 РЕЖИМ РАССЫЛКИ\n\n"
            "Отправьте текст сообщения, и оно будет разослано всем пользователям.\n"
            "Или нажмите «Отменить рассылку» для выхода из режима.",
            reply_markup=cancel_broadcast_kb()
        )
        return
    
    # Есть аргументы - мгновенная рассылка
    await send_broadcast(update, context, msg)

async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, msg: str):
    """Выполняет рассылку сообщения всем пользователям"""
    sent = 0
    failed = 0
    total = len(users)
    
    status_message = await update.message.reply_text(
        f"⏳ Начинаю рассылку...\nВсего пользователей: {total}"
    )
    
    for uid in list(users.keys()):
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"📢 {msg}"
            )
            sent += 1
            if sent % 10 == 0:
                await status_message.edit_text(
                    f"⏳ Рассылка идет...\n"
                    f"Отправлено: {sent}/{total}\n"
                    f"Ошибок: {failed}"
                )
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logging.error(f"Ошибка отправки {uid}: {e}")
    
    await status_message.edit_text(
        f"✅ Рассылка завершена!\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}\n"
        f"👥 Всего в базе: {total}"
    )
    
    # Очищаем режим рассылки если был
    context.user_data[BROADCAST_MODE] = False

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    # Очищаем режим рассылки при входе в админку
    context.user_data[BROADCAST_MODE] = False
    
    await update.message.reply_text(
        "🛠 Админ панель",
        reply_markup=admin_kb()
    )

async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщений в режиме рассылки"""
    uid = str(update.effective_chat.id)
    
    # Проверяем onboarding
    if context.user_data.get("onboarding"):
        await update.message.reply_text(t(uid, "use_buttons"))
        return
    
    # Проверяем права админа и режим рассылки
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.user_data.get(BROADCAST_MODE):
        return
    
    # Получаем сообщение для рассылки
    msg = update.message.text
    
    # Выходим из режима рассылки ПЕРЕД отправкой
    context.user_data[BROADCAST_MODE] = False
    
    # Выполняем рассылку
    await send_broadcast(update, context, msg)

# ---------------- HANDLERS ----------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    q = update.callback_query
    uid = str(q.message.chat.id)
    await q.answer()
    
    # Обработка отмены рассылки (для админа)
    if q.data == "cancel_broadcast":
        if update.effective_user.id != ADMIN_ID:
            await q.answer("❌ Нет доступа", show_alert=True)
            return
        
        if context.user_data.get(BROADCAST_MODE):
            context.user_data[BROADCAST_MODE] = False
            await q.edit_message_text(
                "❌ Рассылка отменена.\n\nВозвращаюсь в админ панель...",
                reply_markup=admin_kb()
            )
        else:
            await q.edit_message_text(
                "🛠 ГЛАВНОЕ МЕНЮ АДМИНА",
                reply_markup=admin_kb()
            )
        return
    
    # Обновляем активность для существующих пользователей
    if uid in users:
        update_activity(update.effective_user, uid)
    
    # ========== ONBOARDING ==========
    
    # Выбор языка при регистрации
    if q.data.startswith("onb_lang_"):
        if context.user_data.get("onboarding") != ONBOARD_LANG:
            await q.answer(t(uid, "action_expired"), show_alert=True)
            return
        
        lang = q.data.split("_")[2]
        context.user_data["new_lang"] = lang
        context.user_data["onboarding"] = ONBOARD_CITY
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Tashkent 🇺🇿", callback_data="onb_city_tashkent")],
            [InlineKeyboardButton("Bremen 🇩🇪", callback_data="onb_city_bremen")]
        ])
        
        await q.edit_message_text(
            "Shaharni tanlang / Выберите город:",
            reply_markup=kb
        )
        return
    
    # Выбор города при регистрации
    if q.data.startswith("onb_city_"):
        if context.user_data.get("onboarding") != ONBOARD_CITY:
            await q.answer(t(uid, "action_expired"), show_alert=True)
            return
        
        city = q.data.split("_")[2]
        lang = context.user_data.get("new_lang", "uz")
        
        # Создаем пользователя
        tashkent_tz = ZoneInfo("Asia/Tashkent")
        now = datetime.now(tashkent_tz).strftime("%Y-%m-%d %H:%M:%S")
        
        users[uid] = {
            "lang": lang,
            "city": city,
            "remind_min": 10,
            "first_name": update.effective_user.first_name,
            "username": update.effective_user.username,
            "joined": now,
            "last_active": now,
            "push_sent": False
        }
        save_users()
        
        # Очищаем onboarding
        context.user_data.clear()
        
        await q.edit_message_text(
            t(uid, "start"),
            reply_markup=main_kb(uid)
        )
        return
    
    # ========== ОСНОВНОЙ ФУНКЦИОНАЛ ==========
    
    # Проверяем, что пользователь существует (для остальных кнопок)
    if uid not in users:
        await q.edit_message_text(t(uid, "please_restart"))
        return
    
    tz = get_tz(uid)
    now = datetime.now(tz)
    city = users[uid]["city"]
    times = get_city_times(city)
    
    # Обратный отсчет до ифтара
    if q.data == "run_countdown":
        today = now.strftime("%Y-%m-%d")
        if today not in times:
            await q.edit_message_text(t(uid, "no_data"), reply_markup=main_kb(uid))
            return
        
        iftar_time = times[today]['iftar']
        iftar_dt = datetime.strptime(
            f"{today} {iftar_time}", 
            "%Y-%m-%d %H:%M"
        ).replace(tzinfo=tz)
        
        diff = iftar_dt - now
        
        if diff.total_seconds() <= 0:
            text = t(uid, "iftar_time_now")
        else:
            total_seconds = int(diff.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            
            text = (
                f"{t(uid, 'iftar_left')}\n\n"
                f"⏳ {hours} {t(uid, 'hour')} {minutes} {t(uid, 'minute')}\n"
                f"🕰 {iftar_time}"
            )
        
        await q.edit_message_text(text, reply_markup=main_kb(uid))
        return
    
    # Сегодня / Завтра
    if q.data.startswith("day_"):
        target = now if q.data == "day_today" else now + timedelta(days=1)
        date_str = target.strftime("%Y-%m-%d")
        
        if date_str in times:
            res = times[date_str]
            pretty_date = format_pretty_date(target, uid)
            text = (
                f"📅 {pretty_date}\n\n"
                f"{t(uid, 'suhoor_until')} {res['suhoor']}\n"
                f"{t(uid, 'iftar_time')} {res['iftar']}"
            )
        else:
            text = t(uid, "no_data")
        
        await q.edit_message_text(text, reply_markup=main_kb(uid))
        return
    
    # Меню настроек
    if q.data == "menu_settings":
        await q.edit_message_text(
            t(uid, "settings_title"), 
            reply_markup=settings_kb(uid)
        )
        return
    
    # Назад в главное меню
    if q.data == "back_main":
        await q.edit_message_text(
            t(uid, "start"), 
            reply_markup=main_kb(uid)
        )
        return
    
    # Смена языка - меню
    if q.data == "set_lang":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
                InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz")
            ]
        ])
        await q.edit_message_text(
            "Выберите язык / Tilni tanlang:", 
            reply_markup=kb
        )
        return
    
    # Применение языка
    if q.data.startswith("lang_"):
        new_lang = q.data.split("_")[1]
        update_user(uid, lang=new_lang)
        await q.edit_message_text(
            t(uid, "lang_changed"), 
            reply_markup=main_kb(uid)
        )
        return
    
    # Смена города - меню
    if q.data == "set_city":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Tashkent 🇺🇿", callback_data="city_tashkent")],
            [InlineKeyboardButton("Bremen 🇩🇪", callback_data="city_bremen")]
        ])
        await q.edit_message_text(
            t(uid, "choose_city"), 
            reply_markup=kb
        )
        return
    
    # Применение города
    if q.data.startswith("city_"):
        new_city = q.data.split("_")[1]
        update_user(uid, city=new_city)
        await q.edit_message_text(
            t(uid, "city_changed"), 
            reply_markup=main_kb(uid)
        )
        return
    
    # Настройка напоминаний - меню
    if q.data == "set_remind":
        current = users[uid].get("remind_min", 10)
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    f"{'✅ ' if current == 5 else ''}5 {t(uid, 'minute')}", 
                    callback_data="rem_5"
                ),
                InlineKeyboardButton(
                    f"{'✅ ' if current == 10 else ''}10 {t(uid, 'minute')}", 
                    callback_data="rem_10"
                ),
                InlineKeyboardButton(
                    f"{'✅ ' if current == 15 else ''}15 {t(uid, 'minute')}", 
                    callback_data="rem_15"
                )
            ],
            [InlineKeyboardButton(t(uid, "back_btn"), callback_data="menu_settings")]
        ])
        await q.edit_message_text(
            t(uid, "choose_rem"), 
            reply_markup=kb
        )
        return
    
    # Применение напоминания
    if q.data.startswith("rem_"):
        minutes = int(q.data.split("_")[1])
        update_user(uid, remind_min=minutes)
        await q.edit_message_text(
            t(uid, "remind_changed"), 
            reply_markup=main_kb(uid)
        )
        return
    
    # ========== АДМИН ПАНЕЛЬ ==========
    
    if not q.data.startswith("admin_"):
        return
    
    if update.effective_user.id != ADMIN_ID:
        await q.answer("❌ Нет доступа", show_alert=True)
        return
    
    # Список пользователей с пагинацией
    if q.data.startswith("admin_users_"):
        parts = q.data.split("_")
        page = int(parts[2]) if len(parts) > 2 else 0
        per_page = 15
        
        user_list = list(users.items())
        total = len(user_list)
        
        start_idx = page * per_page
        end_idx = start_idx + per_page
        page_users = user_list[start_idx:end_idx]
        
        buttons = []
        for user_id, user_data in page_users:
            name = user_data.get("first_name", "User")
            username = user_data.get("username", "")
            display = f"👤 {name}" + (f" (@{username})" if username else "")
            buttons.append([
                InlineKeyboardButton(
                    display[:64],
                    callback_data=f"admin_user_{user_id}_{page}"
                )
            ])
        
        # Навигация
        nav = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    "⬅️ Назад", 
                    callback_data=f"admin_users_{page-1}"
                )
            )
        if end_idx < total:
            nav.append(
                InlineKeyboardButton(
                    "Вперед ➡️", 
                    callback_data=f"admin_users_{page+1}"
                )
            )
        
        if nav:
            buttons.append(nav)
        
        buttons.append([
            InlineKeyboardButton(
                "⬅️ В меню админа", 
                callback_data="admin_back"
            )
        ])
        
        await q.edit_message_text(
            f"👥 ПОЛЬЗОВАТЕЛИ (Страница {page+1}/{((total-1)//per_page)+1})\n"
            f"Всего в базе: {total}", 
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return
    
    # Просмотр конкретного пользователя
    if q.data.startswith("admin_user_"):
        parts = q.data.split("_")
        target_uid = parts[2]
        back_page = parts[3] if len(parts) > 3 else "0"
        
        user = users.get(target_uid)
        if not user:
            await q.edit_message_text(
                "❌ Пользователь не найден", 
                reply_markup=admin_kb()
            )
            return
        
        info = (
            "👤 ДЕТАЛИ ПОЛЬЗОВАТЕЛЯ\n\n"
            f"🆔 ID: <code>{target_uid}</code>\n"
            f"👤 Имя: {user.get('first_name', 'N/A')}\n"
            f"🔗 Username: @{user.get('username', 'N/A')}\n"
            f"🌐 Язык: {user.get('lang', 'N/A')}\n"
            f"🌍 Город: {user.get('city', 'N/A')}\n"
            f"🔔 Напоминание: {user.get('remind_min', 'N/A')} мин\n"
            f"📅 Регистрация: {user.get('joined', 'N/A')}\n"
            f"⚡ Активность: {user.get('last_active', 'N/A')}"
        )
        
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ Назад к списку", 
                    callback_data=f"admin_users_{back_page}"
                )
            ]
        ])
        
        await q.edit_message_text(
            info, 
            reply_markup=kb, 
            parse_mode="HTML"
        )
        return
    
    # Статистика
    if q.data == "admin_stats":
        total_users = len(users)
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        active_today = sum(
            1 for u in users.values() 
            if u.get("last_active", "").startswith(today_str)
        )
        
        # Статистика по языкам
        lang_stats = {}
        city_stats = {}
        
        for u in users.values():
            lang = u.get("lang", "unknown")
            city = u.get("city", "unknown")
            lang_stats[lang] = lang_stats.get(lang, 0) + 1
            city_stats[city] = city_stats.get(city, 0) + 1
        
        text = (
            f"📊 СТАТИСТИКА БОТА\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"🔥 Активны сегодня: {active_today}\n\n"
            f"🌐 Языки:\n"
        )
        
        for lang, count in sorted(lang_stats.items()):
            emoji = "🇷🇺" if lang == "ru" else "🇺🇿" if lang == "uz" else "🌐"
            text += f"  {emoji} {lang}: {count}\n"
        
        text += "\n🌍 Города:\n"
        for city, count in sorted(city_stats.items()):
            emoji = "🇺🇿" if city == "tashkent" else "🇩🇪" if city == "bremen" else "🌍"
            text += f"  {emoji} {city}: {count}\n"
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ В меню админа", callback_data="admin_back")]
        ])
        
        await q.edit_message_text(text, reply_markup=kb)
        return
    
    # Рассылка
    if q.data == "admin_broadcast":
        context.user_data[BROADCAST_MODE] = True
        
        await q.edit_message_text(
            "📢 РЕЖИМ РАССЫЛКИ\n\n"
            "Отправьте текст сообщения, и оно будет разослано всем пользователям.\n"
            "Или нажмите «Отменить рассылку» для выхода из режима.",
            reply_markup=cancel_broadcast_kb()
        )
        return
    
    # Возврат в админ меню
    if q.data == "admin_back":
        context.user_data[BROADCAST_MODE] = False
        await q.edit_message_text(
            "🛠 ГЛАВНОЕ МЕНЮ АДМИНА", 
            reply_markup=admin_kb()
        )
        return

# ---------------- SCHEDULER ----------------
async def send_notification(context: ContextTypes.DEFAULT_TYPE):
    """Отправка уведомления"""
    job = context.job
    try:
        await asyncio.sleep(0.05)
        await context.bot.send_message(
            chat_id=job.user_id, 
            text=job.data,
            parse_mode="HTML"
        )
        logging.info(f"✅ Уведомление отправлено: {job.user_id}")
    except Exception as e:
        if "RetryAfter" in str(e):
            logging.warning(f"⏳ Flood limit для {job.user_id}")
        else:
            logging.error(f"❌ Ошибка отправки {job.user_id}: {e}")

async def run_scheduler(context: ContextTypes.DEFAULT_TYPE):
    """Планировщик напоминаний"""
    tashkent_now = datetime.now(ZoneInfo("Asia/Tashkent"))
    today = tashkent_now.strftime("%Y-%m-%d")
    
    for uid, prefs in list(users.items()):
        # Удаляем старые задачи этого пользователя
        for job in context.job_queue.jobs():
            if job.name and job.name.startswith(f"rem_{uid}_"):
                if today not in job.name:
                    job.schedule_removal()
        
        tz = get_tz(uid)
        now_local = datetime.now(tz)
        city = prefs.get("city", "tashkent")
        times = get_city_times(city)
        
        if today not in times:
            continue
        
        remind_min = prefs.get("remind_min", 10)
        
        for event in ["suhoor", "iftar"]:
            job_name = f"rem_{uid}_{event}_{today}"
            
            if context.job_queue.get_jobs_by_name(job_name):
                continue
            
            event_time = times[today][event]
            event_dt_local = datetime.strptime(
                f"{today} {event_time}", 
                "%Y-%m-%d %H:%M"
            ).replace(tzinfo=tz)
            
            remind_dt_local = event_dt_local - timedelta(minutes=remind_min)
            remind_dt_utc = remind_dt_local.astimezone(ZoneInfo("UTC"))
            
            if remind_dt_utc <= datetime.now(ZoneInfo("UTC")):
                continue
            
            # Формируем текст напоминания
            pretty_date = format_pretty_date(now_local, uid)
            msg = (
                f"📅 {pretty_date}\n\n"
                f"⏳ {t(uid, event+'_rem_text')} {remind_min} {t(uid, 'minute')}!\n"
                f"🕰 {t(uid, 'open_time' if event=='iftar' else 'close_time')}: {event_time}\n\n"
                f"{t(uid, event+'_dua_title')}\n"
                f"<i>{t(uid, event+'_dua')}</i>"
            )
            
            context.job_queue.run_once(
                send_notification,
                when=remind_dt_utc,
                user_id=int(uid),
                data=msg,
                name=job_name
            )
            
            logging.info(f"📅 Запланировано {event} для {uid} на {remind_dt_utc}")
        
        # === НОВОЕ: Проверяем наступление времени события для поздравления ===
        for event in ["suhoor", "iftar"]:
            event_time = times[today][event]
            event_dt = datetime.strptime(
                f"{today} {event_time}", 
                "%Y-%m-%d %H:%M"
            ).replace(tzinfo=tz)
            
            # Если время события наступило (±1 минута) и еще не отправляли
            diff = (now_local - event_dt).total_seconds()
            if 0 <= diff <= 60:  # Наступило менее минуты назад
                congrats_key = f"{event}_congrats_sent_{today}"  # Уникальный ключ на каждый день
                if not prefs.get(congrats_key):
                    # Выбираем правильное сообщение в зависимости от события
                    if event == "suhoor":
                        # Сухур закончился = начался пост
                        congrats_msg = (
                            f"🌅 {t(uid, 'suhoor_ended')}\n\n"
                            f"{t(uid, 'fast_started')}\n\n"
                            f"{t(uid, 'ramadan_congrats')}"
                        )
                    else:
                        # Ифтар закончился = окончание поста
                        congrats_msg = (
                            f"🌙 {t(uid, 'iftar_ended')}\n\n"
                            f"{t(uid, 'fast_ended')}\n\n"
                            f"{t(uid, 'ramadan_congrats')}"
                        )
                    
                    try:
                        await context.bot.send_message(
                            chat_id=int(uid),
                            text=congrats_msg
                        )
                        # Отмечаем что отправили (с датой)
                        update_user(uid, **{congrats_key: True})
                        logging.info(f"🎉 Поздравление {event} для {uid}")
                    except Exception as e:
                        logging.error(f"Ошибка поздравления {uid}: {e}")

# ---------------- MAIN ----------------
async def set_bot_commands(app):
    """Установка команд бота"""
    ru_commands = [
        BotCommand("start", "Главное меню"),
        BotCommand("today", "Время сегодня"),
        BotCommand("settings", "Настройки"),
    ]
    
    uz_commands = [
        BotCommand("start", "Bosh menyu"),
        BotCommand("today", "Bugungi vaqt"),
        BotCommand("settings", "Sozlamalar"),
    ]
    
    await app.bot.set_my_commands(ru_commands, language_code="ru")
    await app.bot.set_my_commands(uz_commands, language_code="uz")

def main():
    """Точка входа"""
    if not TOKEN:
        logging.error("❌ BOT_TOKEN не найден в переменных окружения!")
        return
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.post_init = set_bot_commands
    
    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("admin", admin_panel))
    
    # Обработчики сообщений и кнопок
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_message_handler))
    
    # Планировщик
    app.job_queue.run_repeating(run_scheduler, interval=60, first=5)
    
    logging.info("🚀 БОТ ЗАПУЩЕН")
    app.run_polling()

if __name__ == "__main__":
    main()