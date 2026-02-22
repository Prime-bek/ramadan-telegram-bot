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
        with open("users.json","r",encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users():
    with open("users.json","w",encoding="utf-8") as f:
        json.dump(users,f,ensure_ascii=False,indent=2)

users = load_users()

# ---------------- HELPERS ----------------
def t(uid,key):
    lang = users.get(str(uid),{}).get("lang","ru")
    return TEXTS.get(lang,{}).get(key,key)

def get_city_times(city):
    file=f"times_{city}.json"
    if os.path.exists(file):
        with open(file,"r",encoding="utf-8") as f:
            return json.load(f)
    return {}

def get_tz(uid):
    city = users.get(str(uid),{}).get("city","tashkent")
    return ZoneInfo("Europe/Berlin" if city=="bremen" else "Asia/Tashkent")

# ---------------- KEYBOARDS ----------------
def main_keyboard(uid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(uid,"today"),callback_data="day_today"),
         InlineKeyboardButton(t(uid,"tomorrow"),callback_data="day_tomorrow")],
        [InlineKeyboardButton(t(uid,"countdown"),callback_data="run_countdown")],
        [InlineKeyboardButton("⚙️ Настройки",callback_data="menu_settings")]
    ])

# ---------------- START ----------------
async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):

    user=update.effective_user
    uid=str(update.effective_chat.id)

    if uid not in users:
        users[uid]={
            "lang":"ru",
            "city":"tashkent",
            "remind_min":10,
            "username":user.username,
            "name":user.first_name,
            "joined":datetime.utcnow().isoformat()
        }

    users[uid]["last_seen"]=datetime.utcnow().isoformat()
    save_users()

    await update.message.reply_text(
        t(uid,"start"),
        reply_markup=main_keyboard(uid)
    )

# ---------------- ADMIN STATS ----------------
async def stats(update:Update,context:ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id!=ADMIN_ID:
        return

    total=len(users)

    text=f"📊 BOT STATS\n\n👥 Users: {total}\n\n"

    for uid,data in users.items():
        text+=(
            f"👤 {data.get('name','?')} (@{data.get('username')})\n"
            f"ID: {uid}\n"
            f"🌍 {data.get('city')}\n"
            f"🌐 {data.get('lang')}\n"
            f"🔔 {data.get('remind_min')} min\n\n"
        )

    await update.message.reply_text(text[:4000])

# ---------------- BUTTONS ----------------
async def button_handler(update:Update,context:ContextTypes.DEFAULT_TYPE):

    q=update.callback_query
    await q.answer()

    uid=str(q.message.chat.id)
    tz=get_tz(uid)
    now=datetime.now(tz)

    users[uid]["last_seen"]=datetime.utcnow().isoformat()
    save_users()

    city=users[uid]["city"]
    times=get_city_times(city)

    # COUNTDOWN
    if q.data=="run_countdown":

        today=now.strftime("%Y-%m-%d")

        if today not in times:
            await q.edit_message_text("❌ Нет данных",reply_markup=main_keyboard(uid))
            return

        iftar_str=times[today]["iftar"]

        iftar_dt=datetime.strptime(
            f"{today} {iftar_str}",
            "%Y-%m-%d %H:%M"
        ).replace(tzinfo=tz)

        diff=iftar_dt-now

        if diff.total_seconds()<=0:
            text="🌙 Ифтар уже наступил!"
        else:
            h=diff.seconds//3600
            m=(diff.seconds%3600)//60
            text=f"{t(uid,'iftar_left')}\n\n⏳ {h} {t(uid,'hour')} {m} {t(uid,'minute')}\n🕰 {iftar_str}"

        await q.edit_message_text(text,reply_markup=main_keyboard(uid))

# ---------------- REMINDERS ----------------
async def send_msg(context:ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=context.job.data
    )

async def daily_scheduler(context:ContextTypes.DEFAULT_TYPE):

    # remove only reminder jobs
    for job in list(context.job_queue.jobs()):
        if job.name=="reminder":
            job.schedule_removal()

    for uid,prefs in users.items():

        tz=get_tz(uid)
        now=datetime.now(tz)
        today=now.strftime("%Y-%m-%d")

        times=get_city_times(prefs["city"])
        if today not in times:
            continue

        rm=prefs.get("remind_min",10)

        for event in ["suhoor","iftar"]:

            event_time=times[today][event]

            event_dt=datetime.strptime(
                f"{today} {event_time}",
                "%Y-%m-%d %H:%M"
            ).replace(tzinfo=tz)

            remind_dt=event_dt-timedelta(minutes=rm)

            if remind_dt>now:

                msg=f"🔔 {event.upper()} reminder\n🕰 {event_time}"

                context.job_queue.run_once(
                    send_msg,
                    remind_dt,
                    chat_id=int(uid),
                    data=msg,
                    name="reminder"
                )

# ---------------- MAIN ----------------
def main():

    app=ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("stats",stats))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.job_queue.run_daily(daily_scheduler,time=time(0,5))
    app.job_queue.run_once(daily_scheduler,3)

    print("Bot started")
    app.run_polling()

if __name__=="__main__":
    main()