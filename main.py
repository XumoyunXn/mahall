# mahalla_news_bot.py
import telebot
from telebot import types
import sqlite3
import logging
import os
import time
import sys
import traceback

# ------------------- SOZLAMALAR -------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8462850011:AAH_iecHcprLVhoOoUtzorjBqvd_q0QvLJk")  # tavsiya: tokenni env ga qo'ying
if not TELEGRAM_TOKEN:
    print("❗ TELEGRAM_TOKEN muhim — env ga qo'ying yoki faylda tekshiring.")
    # agar siz to'g'ridan-to'g'ri faylda token qoldirmoqchi bo'lsangiz quyidagi qatorni oching:
    # TELEGRAM_TOKEN = "PASTE_YOUR_TOKEN_HERE"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
DB_PATH = "cases.db"
CHANNELS_DB = "channels.db"

# Adminlar (o'zgartiring)
NEWS_ADMIN_ID = int(os.environ.get("NEWS_ADMIN_ID", "8085370930"))
SUPER_ADMIN_ID = int(os.environ.get("SUPER_ADMIN_ID", "6809167685"))
ADMIN_FOR_PSY_ID = int(os.environ.get("ADMIN_FOR_PSY_ID", "1427892294"))

CATEGORY_ADMINS = {
    "Ayollar muammosi": [ADMIN_FOR_PSY_ID],
    "Oilaviy muammo": [ADMIN_FOR_PSY_ID],
    "Iqtisodiy yordam": [ADMIN_FOR_PSY_ID],
    "Sogʻliq (psixolog)": [ADMIN_FOR_PSY_ID],
    "Boshqa": [ADMIN_FOR_PSY_ID],
}
ADMIN_IDS = set(sum(CATEGORY_ADMINS.values(), []))

_COMMITTEE_CHAT = os.environ.get("COMMITTEE_CHAT_ID", "-1002949455290")
try:
    COMMITTEE_CHAT_ID = int(_COMMITTEE_CHAT)
except:
    COMMITTEE_CHAT_ID = None

# Logging — faylga yozamiz
LOG_FILE = "bot.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ================== DB INIT ==================
def init_db():
    with sqlite3.connect(DB_PATH, timeout=30) as conn:
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
    with sqlite3.connect(CHANNELS_DB, timeout=30) as conn:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS channels (chat_id INTEGER PRIMARY KEY)""")
        conn.commit()

init_db()
init_channels_db()

# ================== CHANNEL FUNKSIYALAR ==================
def add_channel_to_db(chat_id):
    try:
        with sqlite3.connect(CHANNELS_DB, timeout=30) as conn:
            cur = conn.cursor()
            cur.execute("INSERT OR IGNORE INTO channels (chat_id) VALUES (?)", (chat_id,))
            conn.commit()
        logger.info(f"channels.db: qo‘shildi {chat_id}")
    except Exception as e:
        logger.exception(f"add_channel_to_db xato: {e}")

def remove_channel_from_db(chat_id):
    try:
        with sqlite3.connect(CHANNELS_DB, timeout=30) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM channels WHERE chat_id = ?", (chat_id,))
            conn.commit()
        logger.info(f"channels.db: o‘chirildi {chat_id}")
    except Exception as e:
        logger.exception(f"remove_channel_from_db xato: {e}")

def get_all_channels_from_db():
    try:
        with sqlite3.connect(CHANNELS_DB, timeout=30) as conn:
            cur = conn.cursor()
            cur.execute("SELECT chat_id FROM channels")
            return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.exception(f"get_all_channels_from_db xato: {e}")
        return []

def is_bot_admin_in_chat(chat_id):
    try:
        admins = bot.get_chat_administrators(chat_id)
        bot_id = bot.get_me().id
        return any(getattr(adm.user, "id", None) == bot_id for adm in admins)
    except Exception as e:
        logger.debug(f"is_bot_admin_in_chat({chat_id}) error: {e}")
        return False

# ================== MY_CHAT_MEMBER HANDLER (SAFE) ==================
@bot.my_chat_member_handler()
def handle_new_admin_status(update):
    """
    Bot kanalga/admin bo'lganda/chiqib ketganda avtomatik qo'shadi/olib tashlaydi.
    Himoyalangan: update.* elementlari None bo'lishi mumkin, shuning uchun guard bilan.
    """
    try:
        chat = getattr(update, "chat", None)
        new_cm = getattr(update, "new_chat_member", None)
        old_cm = getattr(update, "old_chat_member", None)

        if chat is None or new_cm is None:
            # ba'zan yangilanish boshqa tipda bo'ladi
            return

        bot_info = bot.get_me()
        bot_id = getattr(bot_info, "id", None)
        new_user = getattr(new_cm, "user", None)
        new_status = getattr(new_cm, "status", None)

        # faqat botga tegishli status o'zgarishini ko'ramiz
        if new_user and getattr(new_user, "id", None) == bot_id:
            logger.info(f"my_chat_member: bot status update in chat {chat.id}, status={new_status}")
            if new_status in ("administrator", "creator"):
                add_channel_to_db(chat.id)
                try:
                    bot.send_message(chat.id, "🤖 Bot kanalga ulandi va endi avtomatik post joylay oladi!")
                except Exception as e:
                    logger.debug(f"Bot kanalga xabarnomani yuborada yomm: {e}")
            elif new_status in ("left", "kicked"):
                remove_channel_from_db(chat.id)

    except Exception as e:
        logger.exception(f"handle_new_admin_status xato: {e}")

# ================== CASE FUNKSIYALARI ==================
def save_case(case):
    try:
        with sqlite3.connect(DB_PATH, timeout=30) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO cases (user_id, user_name, created_at, full_name, address, category, description, phone, urgency, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
            """, (
                case.get('user_id'), case.get('user_name'), int(time.time()),
                case.get('full_name'), case.get('address'), case.get('category'),
                case.get('description'), case.get('phone'), case.get('urgency')
            ))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.exception(f"save_case xato: {e}")
        return None

def get_case(case_id):
    try:
        with sqlite3.connect(DB_PATH, timeout=30) as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, user_id, user_name, created_at, full_name, address, category, description, phone, urgency, status, committee_note FROM cases WHERE id = ?", (case_id,))
            row = cur.fetchone()
            if not row:
                return None
            keys = ["id","user_id","user_name","created_at","full_name","address","category","description","phone","urgency","status","committee_note"]
            return dict(zip(keys, row))
    except Exception as e:
        logger.exception(f"get_case xato: {e}")
        return None

def update_case_status(case_id, status, committee_note=None):
    try:
        with sqlite3.connect(DB_PATH, timeout=30) as conn:
            cur = conn.cursor()
            if committee_note is not None:
                cur.execute("UPDATE cases SET status = ?, committee_note = ? WHERE id = ?", (status, committee_note, case_id))
            else:
                cur.execute("UPDATE cases SET status = ? WHERE id = ?", (status, case_id))
            conn.commit()
    except Exception as e:
        logger.exception(f"update_case_status xato: {e}")

# ================== USER FLOW ==================
USER_FLOW = {}
REPORT_STEPS = ['full_name', 'address', 'category', 'description', 'phone', 'urgency']
CATEGORY_OPTIONS = list(CATEGORY_ADMINS.keys())
URGENCY_OPTIONS = ['Past', 'Oʻrta', 'Yuqori (shoshilinch)']

# ================== KOMITETGA YUBORISH ==================
def notify_committee(case_id):
    case = get_case(case_id)
    if not case:
        logger.warning(f"notify_committee: case {case_id} topilmadi")
        return
    text = (
        f"📌 Yangi murojaat (ID: {case_id})\n"
        f"👤 F.O.: {case.get('full_name','-')}\n"
        f"📍 Manzil: {case.get('address','-')}\n"
        f"📂 Toifa: {case.get('category','Boshqa')}\n"
        f"📞 Tel: {case.get('phone','-')}\n"
        f"⚡ Shoshilinchlik: {case.get('urgency','-')}\n\n"
        f"📝 Ta'rif:\n{case.get('description','-')}\n\n"
        f"👤 Foydalanuvchi: @{case.get('user_name') or case.get('user_id')}"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📩 Psixolog jo'natish", callback_data=f"assign_psy|{case_id}"))
    kb.add(types.InlineKeyboardButton("✅ Hal qilindi", callback_data=f"mark_resolved|{case_id}"))
    kb.add(types.InlineKeyboardButton("✉️ Foydalanuvchiga yozish (Admin)", callback_data=f"msg_user|{case_id}"))
    kb.add(types.InlineKeyboardButton("✉️ Foydalanuvchiga yozish (Psixolog)", callback_data=f"msg_user_psy|{case_id}"))

    if COMMITTEE_CHAT_ID:
        try:
            bot.send_message(COMMITTEE_CHAT_ID, text, reply_markup=kb)
        except Exception as e:
            logger.exception(f"notify_committee: {e}")

    for aid in CATEGORY_ADMINS.get(case.get('category'), []):
        try:
            bot.send_message(aid, text, reply_markup=kb)
        except Exception as e:
            logger.exception(f"notify_committee adminga yuborishda xato: {e}")

    if case.get('category') == "Sogʻliq (psixolog)":
        try:
            bot.send_message(ADMIN_FOR_PSY_ID, text, reply_markup=kb)
        except Exception as e:
            logger.exception(f"notify_committee psixologga yuborishda xato: {e}")

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
    if uid in ADMIN_IDS or uid in [SUPER_ADMIN_ID, ADMIN_FOR_PSY_ID, NEWS_ADMIN_ID]:
        bot.send_message(uid, "❌ Siz murojaat yubora olmaysiz.")
        return
    USER_FLOW[uid] = {'step': 0, 'data': {'user_id': uid, 'user_name': message.from_user.username or None}}
    bot.send_message(uid, "Iltimos, to‘liq ismingizni kiriting:")

@bot.message_handler(func=lambda m: m.from_user.id in USER_FLOW)
def report_flow(message):
    uid = message.from_user.id
    flow = USER_FLOW.get(uid)
    if not flow:
        return
    step_idx = flow['step']
    if step_idx >= len(REPORT_STEPS):
        USER_FLOW.pop(uid, None)
        return
    text = (message.text or "").strip()
    key = REPORT_STEPS[step_idx]

    # oddiy validatsiya
    if key == 'category' and text not in CATEGORY_OPTIONS:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for c in CATEGORY_OPTIONS: kb.add(c)
        bot.send_message(uid, "❌ Iltimos toifalardan birini tanlang.", reply_markup=kb)
        return
    if key == 'urgency' and text not in URGENCY_OPTIONS:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for u in URGENCY_OPTIONS: kb.add(u)
        bot.send_message(uid, "❌ Iltimos shoshilinchlikni tanlang.", reply_markup=kb)
        return

    flow['data'][key] = text
    flow['step'] += 1

    # navbatdagi savollar
    next_step = flow['step']
    if next_step == 1:
        bot.send_message(uid, "📍 Manzilingizni kiriting:")
    elif next_step == 2:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for c in CATEGORY_OPTIONS: kb.add(c)
        bot.send_message(uid, "📂 Toifani tanlang:", reply_markup=kb)
    elif next_step == 3:
        bot.send_message(uid, "📝 Muammo tafsilotlarini yozing:", reply_markup=types.ReplyKeyboardRemove())
    elif next_step == 4:
        bot.send_message(uid, "📞 Telefon raqamingizni kiriting:")
    elif next_step == 5:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for u in URGENCY_OPTIONS: kb.add(u)
        bot.send_message(uid, "⚡ Shoshilinchlik darajasini tanlang:", reply_markup=kb)
    elif next_step >= len(REPORT_STEPS):
        case_id = save_case(flow['data'])
        if case_id:
            bot.send_message(uid, f"✅ Rahmat. Xabaringiz qabul qilindi. ID: #{case_id}", reply_markup=types.ReplyKeyboardRemove())
            notify_committee(case_id)
        else:
            bot.send_message(uid, "❌ Murojaatni saqlashda xatolik yuz berdi.")
        USER_FLOW.pop(uid, None)

# ================== CHANNEL REGISTRATION HANDLERS (admin commands) ==================
@bot.message_handler(commands=['addchannel'])
def add_channel_cmd(message):
    if message.from_user.id != NEWS_ADMIN_ID:
        bot.reply_to(message, "❌ Ruxsat yo'q.")
        return
    # agar bu buyruq kanal ichida berilsa
    if message.chat.type in ["group", "supergroup", "channel"]:
        add_channel_to_db(message.chat.id)
        bot.reply_to(message, f"✅ Kanal/guruh ro'yxatga qo'shildi: {message.chat.id}")
        return
    bot.reply_to(message, "Kanalni qo'shish uchun: kanal ichida admin sifatida /addchannel yozing yoki kanal xabarini menga forward qiling.")

@bot.message_handler(func=lambda m: getattr(m, "forward_from_chat", None) is not None)
def handle_forwarded(m):
    # faqat NEWS_ADMIN_ID orqali qo'shamiz
    if m.from_user.id != NEWS_ADMIN_ID:
        return
    fchat = m.forward_from_chat
    if not fchat:
        return
    add_channel_to_db(fchat.id)
    bot.reply_to(m, f"✅ Kanal/guruh ro'yxatga qo'shildi: {fchat.id}")

@bot.message_handler(commands=['delchannel'])
def del_channel_cmd(message):
    if message.from_user.id != NEWS_ADMIN_ID:
        bot.reply_to(message, "❌ Ruxsat yo'q.")
        return
    parts = message.text.strip().split()
    if message.chat.type in ["group", "supergroup", "channel"]:
        cid = message.chat.id
        remove_channel_from_db(cid)
        bot.reply_to(message, f"🗑 Kanal o'chirildi: {cid}")
        return
    if len(parts) == 2:
        try:
            cid = int(parts[1])
            remove_channel_from_db(cid)
            bot.reply_to(message, f"🗑 Kanal o'chirildi: {cid}")
            return
        except:
            pass
    bot.reply_to(message, "❌ Foydalanish: /delchannel yoki kanal ichida /delchannel yoki /delchannel <chat_id>")

@bot.message_handler(commands=['listchannels'])
def list_channels_cmd(message):
    if message.from_user.id != NEWS_ADMIN_ID:
        return
    channels = get_all_channels_from_db()
    if not channels:
        bot.send_message(NEWS_ADMIN_ID, "📭 Ro'yxatda kanal yo'q.")
        return
    text = "📋 Ro'yxatdagi kanallar/guruhlar:\n" + "\n".join(str(c) for c in channels)
    bot.send_message(NEWS_ADMIN_ID, text)

# ================== NEWS ADMIN POST (HAMMASIGA BIRDEK) ==================
@bot.message_handler(func=lambda m: m.from_user.id == NEWS_ADMIN_ID and m.text == "📝 Yangi post qo‘shish")
def admin_post_start(message):
    msg = bot.send_message(NEWS_ADMIN_ID, "📝 Post matnini yuboring (matn yoki rasm).")
    bot.register_next_step_handler(msg, admin_post_send_all)

def admin_post_send_all(message):
    channels = get_all_channels_from_db()
    if not channels:
        bot.send_message(NEWS_ADMIN_ID, "❌ Ro'yxatda kanal yo'q.")
        return

    successful = []
    removed = []
    errors = []

    for chat_id in channels:
        # avval bot adminligini tekshiramiz
        if not is_bot_admin_in_chat(chat_id):
            remove_channel_from_db(chat_id)
            removed.append(chat_id)
            continue
        try:
            if message.content_type == 'text':
                bot.send_message(chat_id, message.text)
            elif message.content_type == 'photo':
                bot.send_photo(chat_id, message.photo[-1].file_id, caption=message.caption or "")
            else:
                # boshqa media turlarini hozircha matn sifatida yuboramiz
                bot.send_message(chat_id, "📢 Yangilik (admin tomonidan yuborildi) — media turi qo'llab-quvvatlanmadi.")
            successful.append(chat_id)
        except Exception as e:
            logger.exception(f"admin_post_send_all to {chat_id} failed: {e}")
            errors.append((chat_id, str(e)))

    res = f"✅ Post yuborildi: {len(successful)} ta kanal/guruh.\n"
    if removed:
        res += "❗ Quyidagi kanallar ro'yxatdan olib tashlandi (bot admin emas):\n" + "\n".join(str(x) for x in removed) + "\n"
    if errors:
        res += "⚠️ Ba'zi chatlarda xatoliklar:\n" + "\n".join(f"{c}: {err}" for c,err in errors)
    bot.send_message(NEWS_ADMIN_ID, res)

# ================== CALLBACKS (soddalashtirilgan) ==================
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    data = call.data or ""
    caller_id = call.from_user.id
    call_id = call.id
    if "|" in data:
        action, case_id_str = data.split("|", 1)
        try:
            case_id = int(case_id_str)
        except ValueError:
            bot.answer_callback_query(call_id, "❌ Noto'g'ri ID")
            return
        case = get_case(case_id)
        if not case:
            bot.answer_callback_query(call_id, "❌ Case topilmadi")
            return

        if action == "mark_resolved":
            update_case_status(case_id, "resolved")
            bot.answer_callback_query(call_id, "✅ Hal qilindi deb belgilandi")
            return

        if action == "assign_psy":
            bot.answer_callback_query(call_id, "📌 Psixologga yuborildi")
            # psixologga yuborish logikasi shu yerda
            try:
                bot.send_message(ADMIN_FOR_PSY_ID, f"📌 ID: {case_id}\nF.O.: {case.get('full_name')}\n{case.get('description')}")
                bot.send_message(caller_id, "✅ Psixologga yuborildi")
            except Exception as e:
                logger.exception(f"assign_psy xato: {e}")
            return

# ================== RUN BOT ==================
if __name__ == "__main__":
    try:
        logger.info("🤖 Bot ishga tushdi...")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        logger.exception(f"Bot ishlayotganda kutilmagan xato: {e}")
        traceback.print_exc()
