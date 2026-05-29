"""
Kundalik Reja Telegram Bot (Groq versiyasi - bepul!)
"""

import os
import asyncio
import logging
from datetime import datetime, time
import pytz
from groq import Groq

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

from database import Database

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Tashkent")
MORNING_HOUR = int(os.environ.get("MORNING_HOUR", "8"))
MORNING_MINUTE = int(os.environ.get("MORNING_MINUTE", "0"))

db = Database("tasks.db")
groq_client = Groq(api_key=GROQ_API_KEY)

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📋 Vazifalar", callback_data="list_tasks"),
         InlineKeyboardButton("➕ Vazifa qo'sh", callback_data="add_task")],
        [InlineKeyboardButton("⏰ Eslatma qo'sh", callback_data="add_reminder"),
         InlineKeyboardButton("🤖 AI bilan reja tuz", callback_data="ai_plan")],
        [InlineKeyboardButton("✅ Bajarilganlar", callback_data="done_tasks"),
         InlineKeyboardButton("🗑 Tozalash", callback_data="clear_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def format_task_list(tasks, title="📋 Vazifalar"):
    if not tasks:
        return f"{title}\n\n⚠️ Hozircha bo'sh."
    lines = [f"{title}\n"]
    for t in tasks:
        status = "✅" if t["done"] else "🔲"
        priority_emoji = {"yuqori": "🔴", "o'rta": "🟡", "past": "🟢"}.get(t.get("priority", "o'rta"), "⚪")
        deadline_str = f" | ⏰ {t['deadline']}" if t.get("deadline") else ""
        lines.append(f"{status} {priority_emoji} {t['title']}{deadline_str}")
        if t.get("description"):
            lines.append(f"   ↳ {t['description']}")
    return "\n".join(lines)

def ask_ai(user_id, user_message):
    history = db.get_conversation(user_id, limit=10)
    tasks = db.get_tasks(user_id, done=False)
    task_summary = format_task_list(tasks, "Joriy vazifalar")
    
    system_prompt = f"""Sen o'zbek tilida gaplashadigan shaxsiy kundalik reja assistantsan.
Qisqa, aniq va foydali javob ber.

{task_summary}

Bugungi sana: {datetime.now(pytz.timezone(TIMEZONE)).strftime('%Y-%m-%d, %A')}"""

    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_message})

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=1000,
    )
    reply = response.choices[0].message.content
    db.save_conversation(user_id, "user", user_message)
    db.save_conversation(user_id, "assistant", reply)
    return reply

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.ensure_user(user.id, user.first_name)
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz).strftime("%H:%M")
    text = (
        f"👋 Salom, *{user.first_name}*!\n\n"
        f"Men sizning shaxsiy *reja assistantingizman*. 🤖\n\n"
        f"🕐 Hozirgi vaqt: {now} ({TIMEZONE})\n\n"
        f"Nima qila olaman:\n"
        f"📋 Vazifalarni saqlash va kuzatish\n"
        f"⏰ Eslatmalar yuborish\n"
        f"🌅 Har kuni ertalab reja yuborish\n"
        f"🤖 AI bilan reja tuzish\n\n"
        f"Quyidagi tugmalardan foydalaning:"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    tasks = db.get_tasks(uid, done=False)
    await update.message.reply_text(format_task_list(tasks), reply_markup=get_main_keyboard())

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = " ".join(context.args).split("|") if context.args else []
    if not args or not args[0].strip():
        await update.message.reply_text(
            "📝 *Vazifa qo'shish:*\n\n`/add Vazifa nomi`\n`/add Vazifa nomi | tavsif | 2024-12-31 | yuqori`",
            parse_mode="Markdown"
        )
        return
    title = args[0].strip()
    description = args[1].strip() if len(args) > 1 else ""
    deadline = args[2].strip() if len(args) > 2 else ""
    priority = args[3].strip() if len(args) > 3 else "o'rta"
    db.add_task(uid, title, description, deadline, priority)
    await update.message.reply_text(f"✅ *{title}* vazifasi qo'shildi!", parse_mode="Markdown")

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        tasks = db.get_tasks(uid, done=False)
        if not tasks:
            await update.message.reply_text("✅ Barcha vazifalar bajarilgan!")
            return
        lines = ["Qaysi vazifani belgilash? ID ni yozing:\n"]
        for t in tasks:
            lines.append(f"*{t['id']}* — {t['title']}")
        lines.append("\nMasalan: `/done 3`")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return
    try:
        task = db.mark_done(uid, int(context.args[0]))
        if task:
            await update.message.reply_text(f"🎉 *{task['title']}* bajarildi!", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Vazifa topilmadi.")
    except ValueError:
        await update.message.reply_text("❌ Raqam kiriting. Masalan: `/done 3`", parse_mode="Markdown")

async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if len(context.args) < 2:
        await update.message.reply_text("⏰ Format: `/remind 14:30 Dori iching`", parse_mode="Markdown")
        return
    time_str = context.args[0]
    message = " ".join(context.args[1:])
    try:
        hour, minute = map(int, time_str.split(":"))
        tz = pytz.timezone(TIMEZONE)
        now = datetime.now(tz)
        remind_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if remind_time <= now:
            from datetime import timedelta
            remind_time += timedelta(days=1)
        delay = (remind_time - now).total_seconds()
        context.job_queue.run_once(
            send_reminder, when=delay,
            data={"user_id": uid, "message": message, "time_str": time_str}
        )
        db.add_reminder(uid, time_str, message)
        await update.message.reply_text(f"⏰ Eslatma qo'yildi: *{time_str}* — {message}", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("❌ Format: `/remind 14:30 Xabar`", parse_mode="Markdown")

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    await context.bot.send_message(
        chat_id=data["user_id"],
        text=f"🔔 *Eslatma!*\n\n{data['message']}\n\n🕐 {data['time_str']}",
        parse_mode="Markdown"
    )

async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await send_morning_plan(context, uid, update.message)

async def send_morning_plan(context, user_id, message=None):
    tasks = db.get_tasks(user_id, done=False)
    tz = pytz.timezone(TIMEZONE)
    today = datetime.now(tz).strftime("%d.%m.%Y, %A")
    task_list = format_task_list(tasks, "")
    prompt = f"Bugun {today}. Vazifalar:\n{task_list}\n\nQisqa motivatsion xabar va eng muhim 3 vazifani ajrat." if tasks else f"Bugun {today}. Vazifa yo'q. Foydali maslahat ber."
    ai_reply = ask_ai(user_id, prompt)
    text = f"🌅 *Xayrli tong!*\n📅 {today}\n\n{ai_reply}\n\n━━━━━━━━━━━━━━━\n{format_task_list(tasks)}"
    if message:
        await message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await context.bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    if data == "list_tasks":
        tasks = db.get_tasks(uid, done=False)
        await query.message.reply_text(format_task_list(tasks), reply_markup=get_main_keyboard())
    elif data == "add_task":
        context.user_data["waiting_for"] = "new_task"
        await query.message.reply_text("📝 Vazifa nomini yozing:")
    elif data == "add_reminder":
        context.user_data["waiting_for"] = "new_reminder"
        await query.message.reply_text("⏰ Format: `14:30 Dori iching`", parse_mode="Markdown")
    elif data == "ai_plan":
        context.user_data["waiting_for"] = "ai_chat"
        await query.message.reply_text("🤖 Savolingizni yozing! Masalan: \"Bugungi kunni rejalashtir\"")
    elif data == "done_tasks":
        tasks = db.get_tasks(uid, done=True)
        await query.message.reply_text(format_task_list(tasks, "✅ Bajarilgan vazifalar"))
    elif data == "clear_menu":
        keyboard = [
            [InlineKeyboardButton("🗑 Bajarilganlarni o'chir", callback_data="clear_done")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")],
        ]
        await query.message.reply_text("Nimani tozalamoqchisiz?", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "clear_done":
        count = db.clear_done_tasks(uid)
        await query.message.reply_text(f"✅ {count} ta bajarilgan vazifa o'chirildi.")
    elif data == "cancel":
        await query.message.reply_text("❌ Bekor qilindi.", reply_markup=get_main_keyboard())
    elif data.startswith("priority_"):
        priority = data.replace("priority_", "")
        title = context.user_data.get("new_task_title", "")
        desc = context.user_data.get("new_task_desc", "")
        deadline = context.user_data.get("new_task_deadline", "")
        db.add_task(uid, title, desc, deadline, priority)
        context.user_data["waiting_for"] = None
        await query.message.reply_text(f"✅ *{title}* qo'shildi!", parse_mode="Markdown", reply_markup=get_main_keyboard())

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    waiting = context.user_data.get("waiting_for")

    if waiting == "new_task":
        context.user_data["new_task_title"] = text
        context.user_data["waiting_for"] = "new_task_desc"
        await update.message.reply_text(f"✅ Nom: *{text}*\n\nTavsif yozing (yoki /skip):", parse_mode="Markdown")
    elif waiting == "new_task_desc":
        context.user_data["new_task_desc"] = "" if text == "/skip" else text
        context.user_data["waiting_for"] = "new_task_deadline"
        await update.message.reply_text("📅 Muddat kiriting (yoki /skip):\nFormat: `2024-12-31`", parse_mode="Markdown")
    elif waiting == "new_task_deadline":
        context.user_data["new_task_deadline"] = "" if text == "/skip" else text
        context.user_data["waiting_for"] = "new_task_priority"
        keyboard = [[
            InlineKeyboardButton("🔴 Yuqori", callback_data="priority_yuqori"),
            InlineKeyboardButton("🟡 O'rta", callback_data="priority_o'rta"),
            InlineKeyboardButton("🟢 Past", callback_data="priority_past"),
        ]]
        await update.message.reply_text("🎯 Muhimlikni tanlang:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif waiting == "new_reminder":
        parts = text.split(" ", 1)
        if len(parts) >= 2:
            time_str, msg = parts[0], parts[1]
            try:
                hour, minute = map(int, time_str.split(":"))
                tz = pytz.timezone(TIMEZONE)
                now = datetime.now(tz)
                remind_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if remind_time <= now:
                    from datetime import timedelta
                    remind_time += timedelta(days=1)
                delay = (remind_time - now).total_seconds()
                context.job_queue.run_once(send_reminder, when=delay, data={"user_id": uid, "message": msg, "time_str": time_str})
                db.add_reminder(uid, time_str, msg)
                context.user_data["waiting_for"] = None
                await update.message.reply_text(f"⏰ Eslatma: *{time_str}* — {msg}", parse_mode="Markdown", reply_markup=get_main_keyboard())
            except:
                await update.message.reply_text("❌ Format: `14:30 Xabar`", parse_mode="Markdown")
        else:
            await update.message.reply_text("Format: `14:30 Eslatma matni`", parse_mode="Markdown")
    else:
        try:
            reply = ask_ai(uid, text)
            await update.message.reply_text(reply, parse_mode="Markdown", reply_markup=get_main_keyboard())
        except Exception as e:
            logger.error(f"AI error: {e}")
            await update.message.reply_text("❌ Qayta urinib ko'ring.")

async def morning_job(context: ContextTypes.DEFAULT_TYPE):
    for user in db.get_all_users():
        try:
            await send_morning_plan(context, user["id"])
        except Exception as e:
            logger.error(f"Morning plan error: {e}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", cmd_tasks))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("remind", cmd_remind))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    tz = pytz.timezone(TIMEZONE)
    app.job_queue.run_daily(morning_job, time=time(hour=MORNING_HOUR, minute=MORNING_MINUTE, tzinfo=tz))
    logger.info(f"Bot ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
