# mahalla_news_bot.py
import telebot
from telebot import types
import sqlite3
import logging
import os
import time

# ------------------- SOZLAMALAR -------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8462850011:AAH_iecHcprLVhoOoUtzorjBqvd_q0QvLJk")
bot = telebot.TeleBot(TELEGRAM_TOKEN)
DB_PATH = "cases.db"
CHANNELS_DB = "channels.db"

# Adminlar
NEWS_ADMIN_ID = 8085370930
SUPER_ADMIN_ID = 6809167685
ADMIN_FOR_PSY_ID = 1427892294

CATEGORY_ADMINS = {
    "Ayollar muammosi": [1427892294],
    "Oilaviy muammo": [1427892294],
    "Iqtisodiy yordam": [1427892294],
    "Sogʻliq (psixolog)": [1427892294],
    "Boshqa": [1427892294],
}
ADMIN_IDS = set(sum(CATEGORY_ADMINS.values(), []))

_COMMITTEE_CHAT = os.environ.get("COMMITTEE_CHAT_ID", "-1002949455290")
try:
    COMMITTEE_CHAT_ID = int(_COMMITTEE_CHAT)
except:
    COMMITTEE_CHAT_ID = None

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== DB INIT ==================
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            created_at INTEGER,
            full_name TEXT,
            address TEXT,
            category TEXT,
            description TEXT,
            phone TEXT,
            urgency TEXT,
            status TEXT DEFAULT 'new',
            committee_note TEXT
        )
        """)
        conn.commit()

def init_channels_db():
    with sqlite3.connect(CHANNELS_DB) as conn:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS channels (chat_id INTEGER PRIMARY KEY)""")
        conn.commit()

init_db()
init_channels_db()

# ================== CHANNEL FUNKSIYALAR ==================
def add_channel_to_db(chat_id):
    with sqlite3.connect(CHANNELS_DB) as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO channels (chat_id) VALUES (?)", (chat_id,))
        conn.commit()

def remove_channel_from_db(chat_id):
    with sqlite3.connect(CHANNELS_DB) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM channels WHERE chat_id = ?", (chat_id,))
        conn.commit()

def get_all_channels_from_db():
    with sqlite3.connect(CHANNELS_DB) as conn:
        cur = conn.cursor()
        cur.execute("SELECT chat_id FROM channels")
        return [row[0] for row in cur.fetchall()]

def is_bot_admin_in_chat(chat_id):
    try:
        admins = bot.get_chat_administrators(chat_id)
        bot_id = bot.get_me().id
        return any(adm.user.id == bot_id for adm in admins)
    except Exception as e:
        logger.warning(f"Admin tekshirishda xato: {e}")
        return False

# ================== KANAL ADMINGA QO‘SHILGANI ANIQLANADI ==================
@bot.my_chat_member_handler()
def handle_new_admin_status(update):
    chat = update.chat
    if chat.type == "channel" and update.new_chat_member.status in ["administrator", "member"]:
        add_channel_to_db(chat.id)
        bot.send_message(chat.id, "🤖 Bot kanalga ulandi va endi avtomatik post joylaydi!")
        logger.info(f"Bot kanalga qo‘shildi: {chat.title} ({chat.id})")

# ================== CASE FUNKSIYALAR ==================
def save_case(case):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cases (user_id, user_name, created_at, full_name, address, category, description, phone, urgency, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
        """, (
            case['user_id'], case['user_name'], int(time.time()),
            case['full_name'], case['address'], case['category'],
            case['description'], case['phone'], case['urgency']
        ))
        conn.commit()
        return cur.lastrowid

def get_case(case_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM cases WHERE id=?", (case_id,))
        row = cur.fetchone()
        if not row: return None
        keys = ["id","user_id","user_name","created_at","full_name","address","category","description","phone","urgency","status","committee_note"]
        return dict(zip(keys, row))

def update_case_status(case_id, status, committee_note=None):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        if committee_note:
            cur.execute("UPDATE cases SET status=?, committee_note=? WHERE id=?", (status, committee_note, case_id))
        else:
            cur.execute("UPDATE cases SET status=? WHERE id=?", (status, case_id))
        conn.commit()

# ================== USER FLOW ==================
USER_FLOW = {}
REPORT_STEPS = ['full_name', 'address', 'category', 'description', 'phone', 'urgency']
CATEGORY_OPTIONS = list(CATEGORY_ADMINS.keys())
URGENCY_OPTIONS = ['Past', 'Oʻrta', 'Yuqori (shoshilinch)']

# ================== KOMITETGA YUBORISH ==================
def notify_committee(case_id):
    case = get_case(case_id)
    if not case: return
    text = (
        f"📌 Yangi murojaat (ID: {case_id})\n"
        f"👤 F.O.: {case['full_name']}\n"
        f"📍 Manzil: {case['address']}\n"
        f"📂 Toifa: {case['category']}\n"
        f"📞 Tel: {case['phone']}\n"
        f"⚡ Shoshilinchlik: {case['urgency']}\n\n"
        f"📝 Ta'rif:\n{case['description']}"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Hal qilindi", callback_data=f"mark_resolved|{case_id}"))
    if COMMITTEE_CHAT_ID:
        bot.send_message(COMMITTEE_CHAT_ID, text, reply_markup=kb)

# ================== /start ==================
@bot.message_handler(commands=['start'])
def start_handler(message):
    uid = message.from_user.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if uid == NEWS_ADMIN_ID:
        markup.add("📝 Yangi post qo‘shish")
        bot.send_message(uid, "Assalomu alaykum! Siz yangilik yuborishingiz mumkin.", reply_markup=markup)
    else:
        markup.add("✍️ Murojaat yuborish")
        bot.send_message(uid, "👋 Salom! Men *Mahalla yordam botiman.*", parse_mode="Markdown", reply_markup=markup)

# ================== FOYDALANUVCHI MUROJAATI ==================
@bot.message_handler(func=lambda m: m.text == "✍️ Murojaat yuborish")
def start_report(message):
    uid = message.from_user.id
    USER_FLOW[uid] = {'step': 0, 'data': {'user_id': uid, 'user_name': message.from_user.username}}
    bot.send_message(uid, "Iltimos, to‘liq ismingizni kiriting:")

@bot.message_handler(func=lambda m: m.from_user.id in USER_FLOW)
def report_flow(message):
    uid = message.from_user.id
    flow = USER_FLOW[uid]
    step = flow['step']
    text = message.text.strip()
    key = REPORT_STEPS[step]

    flow['data'][key] = text
    flow['step'] += 1

    if key == 'full_name':
        bot.send_message(uid, "📍 Manzilingizni kiriting:")
    elif key == 'address':
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for c in CATEGORY_OPTIONS: kb.add(c)
        bot.send_message(uid, "📂 Toifani tanlang:", reply_markup=kb)
    elif key == 'category':
        bot.send_message(uid, "📝 Muammo tafsilotlarini yozing:", reply_markup=types.ReplyKeyboardRemove())
    elif key == 'description':
        bot.send_message(uid, "📞 Telefon raqamingizni kiriting:")
    elif key == 'phone':
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for u in URGENCY_OPTIONS: kb.add(u)
        bot.send_message(uid, "⚡ Shoshilinchlik darajasini tanlang:", reply_markup=kb)
    elif key == 'urgency':
        case_id = save_case(flow['data'])
        bot.send_message(uid, f"✅ Rahmat. Xabaringiz qabul qilindi. ID: #{case_id}")
        notify_committee(case_id)
        USER_FLOW.pop(uid)

# ================== NEWS ADMIN POST ==================
@bot.message_handler(func=lambda m: m.from_user.id == NEWS_ADMIN_ID and m.text == "📝 Yangi post qo‘shish")
def admin_post_start(message):
    msg = bot.send_message(NEWS_ADMIN_ID, "📝 Post matnini yuboring (matn yoki rasm).")
    bot.register_next_step_handler(msg, admin_post_send_all)

def admin_post_send_all(message):
    channels = get_all_channels_from_db()
    if not channels:
        bot.send_message(NEWS_ADMIN_ID, "❌ Ro'yxatda kanal yo'q.")
        return

    for chat_id in channels:
        if not is_bot_admin_in_chat(chat_id):
            remove_channel_from_db(chat_id)
            continue
        try:
            if message.content_type == 'text':
                bot.send_message(chat_id, message.text)
            elif message.content_type == 'photo':
                bot.send_photo(chat_id, message.photo[-1].file_id, caption=message.caption or "")
        except Exception as e:
            logger.warning(f"Kanalga yuborishda xato {chat_id}: {e}")

    bot.send_message(NEWS_ADMIN_ID, "✅ Post barcha kanallarga yuborildi.")

# ================== BOTNI ISHGA TUSHURISH ==================
if __name__ == "__main__":
    print("🤖 Bot ishga tushdi...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
