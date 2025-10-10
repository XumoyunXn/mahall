"""
Professional Telegram Bot (Full Extended Version)
- Superadmin: statistikani ko‘radi
- Yangilik admin: kanal/guruhga yangilik yuboradi
- Bo‘lim adminlar: faqat o‘z yo‘nalishidagi murojaatlarga javob beradi
- Foydalanuvchilar: murojaat yuboradi
- Har bir xabar, foydalanuvchi, kanal/guruh bazaga yoziladi
"""

import os
import sqlite3
import logging
from datetime import datetime
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
)
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

# --------------- CONFIG ----------------
TOKEN = "8462850011:AAH_iecHcprLVhoOoUtzorjBqvd_q0QvLJk"
SUPER_ADMIN_ID = 6809167685
NEWS_ADMIN_IDS = [8085370930]
ADMIN_FOR_PSY_ID = 1427892294

DB_PATH = "data/bot_full.db"

ADMINS = {
    "Ayollar muammosi": [1427892294],
    "Oilaviy muammo": [1427892294],
    "Iqtisodiy yordam": [1427892294],
    "Sogʻliq (psixolog)": [ADMIN_FOR_PSY_ID],
    "Boshqa": [1427892294],
}

# --------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --------------- DATABASE ----------------
def ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        name TEXT,
        mahalla TEXT,
        phone TEXT,
        last_message TEXT,
        last_seen TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS reports(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        category TEXT,
        urgency TEXT,
        details TEXT,
        status TEXT DEFAULT 'jarayonda',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER,
        target_id INTEGER,
        role TEXT,
        message_text TEXT,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS channels(
        chat_id INTEGER PRIMARY KEY,
        title TEXT,
        type TEXT,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()
    conn.close()

def db_execute(query, params=(), fetchone=False, fetchall=False):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(query, params)
    result = None
    if fetchone:
        result = c.fetchone()
    elif fetchall:
        result = c.fetchall()
    conn.commit()
    conn.close()
    return result

# --------------- CHANNELS ----------------
def add_channel(chat_id, title, chat_type):
    db_execute("INSERT OR REPLACE INTO channels(chat_id, title, type) VALUES(?,?,?)", (chat_id, title, chat_type))

def remove_channel(chat_id):
    db_execute("DELETE FROM channels WHERE chat_id=?", (chat_id,))

def list_channels():
    return db_execute("SELECT chat_id, title FROM channels", fetchall=True) or []

# --------------- STATES ----------------
(ASK_NAME, ASK_MAHALLA, ASK_PHONE, ASK_CATEGORY, ASK_DETAILS, ASK_URGENCY, NEWS_TEXT) = range(7)

# --------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # Super admin
    if uid == SUPER_ADMIN_ID:
        kb = ReplyKeyboardMarkup([["📊 Statistika"]], resize_keyboard=True)
        await update.message.reply_text("Assalomu alaykum, Super Admin!", reply_markup=kb)
        return

    # Yangilik admin
    if uid in NEWS_ADMIN_IDS:
        kb = ReplyKeyboardMarkup([["📰 Yangilik yuborish"]], resize_keyboard=True)
        await update.message.reply_text("Assalomu alaykum, Yangilik Admin!", reply_markup=kb)
        return

    # Bo‘lim admin
    for cat, admins in ADMINS.items():
        if uid in admins:
            await update.message.reply_text(f"Siz '{cat}' bo‘limi adminisiz.")
            return

    # Oddiy foydalanuvchi
    await update.message.reply_text("Ismingizni kiriting:", reply_markup=ReplyKeyboardRemove())
    return ASK_NAME

# --------------- SUPER ADMIN ----------------
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPER_ADMIN_ID:
        return await update.message.reply_text("❌ Sizda bu buyruq uchun ruxsat yo‘q.")
    users = db_execute("SELECT COUNT(*) FROM users", fetchone=True)[0]
    total = db_execute("SELECT COUNT(*) FROM reports", fetchone=True)[0]
    msgs = db_execute("SELECT COUNT(*) FROM messages", fetchone=True)[0]
    channels = db_execute("SELECT COUNT(*) FROM channels", fetchone=True)[0]
    await update.message.reply_text(
        f"📊 *Statistika:*\n\n"
        f"👥 Foydalanuvchilar: {users}\n"
        f"📩 Murojaatlar: {total}\n"
        f"💬 Yozishmalar: {msgs}\n"
        f"📢 Kanallar / Guruhlar: {channels}",
        parse_mode=ParseMode.MARKDOWN
    )

# --------------- YANGILIK ADMIN ----------------
async def ask_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in NEWS_ADMIN_IDS:
        return
    await update.message.reply_text("Yuboriladigan yangilik matnini kiriting:",
                                    reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True))
    context.user_data["awaiting_news"] = True
    return NEWS_TEXT

async def receive_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_news"):
        return
    msg = update.message
    count = 0
    for chat_id, title in list_channels():
        try:
            await context.bot.copy_message(chat_id=chat_id, from_chat_id=msg.chat.id, message_id=msg.message_id)
            count += 1
        except Exception as e:
            logger.warning(f"Yuborilmadi {chat_id}: {e}")
    await update.message.reply_text(f"✅ Yangilik {count} ta joyga yuborildi.")
    context.user_data.pop("awaiting_news", None)
    return ConversationHandler.END

# --------------- USER FLOW ----------------
async def ask_name(update, context):
    uid = update.effective_user.id
    db_execute("INSERT OR REPLACE INTO users(user_id, username, name, last_seen) VALUES(?,?,?,?)",
               (uid, update.effective_user.username or "", update.message.text, datetime.now()))
    await update.message.reply_text("🏘 Mahallangizni kiriting:")
    return ASK_MAHALLA

async def ask_mahalla(update, context):
    db_execute("UPDATE users SET mahalla=? WHERE user_id=?", (update.message.text, update.effective_user.id))
    await update.message.reply_text("📞 Telefon raqamingizni kiriting:")
    return ASK_PHONE

async def ask_phone(update, context):
    db_execute("UPDATE users SET phone=? WHERE user_id=?", (update.message.text, update.effective_user.id))
    kb = ReplyKeyboardMarkup([[c] for c in ADMINS.keys()], resize_keyboard=True)
    await update.message.reply_text("🧩 Muammo turini tanlang:", reply_markup=kb)
    return ASK_CATEGORY

async def ask_category(update, context):
    category = update.message.text
    if category not in ADMINS:
        return await update.message.reply_text("Iltimos, menyudan tanlang.")
    context.user_data["report"] = {"category": category}
    await update.message.reply_text("📝 Muammo tafsilotlarini yozing:", reply_markup=ReplyKeyboardRemove())
    return ASK_DETAILS

async def ask_details(update, context):
    context.user_data["report"]["details"] = update.message.text
    kb = ReplyKeyboardMarkup([["Juda shoshilinch", "O‘rtacha", "Oddiy"]], resize_keyboard=True)
    await update.message.reply_text("⚡ Muhimlik darajasini tanlang:", reply_markup=kb)
    return ASK_URGENCY

async def ask_urgency(update, context):
    urgency = update.message.text
    rep = context.user_data["report"]
    uid = update.effective_user.id
    db_execute("INSERT INTO reports(user_id, category, urgency, details) VALUES(?,?,?,?)",
               (uid, rep["category"], urgency, rep["details"]))

    # Foydalanuvchi ma’lumotini olish
    user = db_execute("SELECT name, mahalla, phone FROM users WHERE user_id=?", (uid,), fetchone=True)
    name, mahalla, phone = user

    msg_text = (
        f"📩 *Yangi murojaat:*\n\n"
        f"👤 Ism: {escape_markdown(name)}\n"
        f"🏘 Mahalla: {escape_markdown(mahalla)}\n"
        f"📞 Tel: {escape_markdown(phone)}\n"
        f"💬 Bo‘lim: {escape_markdown(rep['category'])}\n"
        f"⚡ Daraja: {escape_markdown(urgency)}\n"
        f"📝 Tafsilot: {escape_markdown(rep['details'])}\n"
    )

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✉️ Foydalanuvchiga yozish", callback_data=f"msg_{uid}")]
    ])

    for admin_id in ADMINS.get(rep["category"], []):
        await context.bot.send_message(chat_id=admin_id, text=msg_text,
                                       parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    await update.message.reply_text("✅ Murojaatingiz qabul qilindi. Rahmat!")
    return ConversationHandler.END

# --------------- ADMIN - REPLY ----------------
async def admin_reply_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_id = int(query.data.split("_")[1])
    admin_id = query.from_user.id

    allowed = any(admin_id in admins for admins in ADMINS.values())
    if not allowed:
        return await query.message.reply_text("❌ Sizda bu foydalanuvchiga yozish uchun ruxsat yo‘q.")

    context.user_data["reply_to"] = target_id
    await query.message.reply_text("✉️ Foydalanuvchiga yuboriladigan xabarni kiriting:")

async def admin_send_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "reply_to" not in context.user_data:
        return
    target_id = context.user_data.pop("reply_to")
    msg = update.message.text
    admin_id = update.effective_user.id

    try:
        await context.bot.send_message(chat_id=target_id, text=f"📬 *Admindan xabar:*\n\n{msg}",
                                       parse_mode=ParseMode.MARKDOWN)
        await update.message.reply_text("✅ Xabar foydalanuvchiga yuborildi.")
        db_execute("INSERT INTO messages(sender_id, target_id, role, message_text) VALUES(?,?,?,?)",
                   (admin_id, target_id, 'admin', msg))
    except Exception as e:
        await update.message.reply_text(f"❌ Xabar yuborilmadi.\n{e}")

# --------------- CHANNEL MONITOR ----------------
async def my_chat_member(update, context):
    chat = update.my_chat_member.chat
    status = update.my_chat_member.new_chat_member.status
    if status in ("administrator", "creator"):
        add_channel(chat.id, getattr(chat, "title", ""), chat.type)
    elif status in ("left", "kicked"):
        remove_channel(chat.id)

# --------------- MAIN ----------------
def main():
    ensure_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(ChatMemberHandler(my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(admin_reply_button, pattern=r"^msg_\d+$"))

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_MAHALLA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_mahalla)],
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)],
            ASK_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_category)],
            ASK_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_details)],
            ASK_URGENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_urgency)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(conv)

    news_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📰 Yangilik yuborish$"), ask_news)],
        states={NEWS_TEXT: [MessageHandler(filters.ALL, receive_news)]},
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(news_conv)

    app.add_handler(MessageHandler(filters.Regex("^📊 Statistika$"), show_stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_send_to_user))
    app.add_handler(CommandHandler("start", start))

    print("✅ Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
