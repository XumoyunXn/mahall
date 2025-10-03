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

# Adminlar va psixolog
NEWS_ADMIN_ID = 8085370930
SUPER_ADMIN_ID = 6809167685
ADMIN_FOR_PSY_ID = 1427892294  # Psixolog admin id
CATEGORY_ADMINS = {
    "Ayollar muammosi": [1427892294],
    "Oilaviy muammo": [1427892294],
    "Iqtisodiy yordam": [1427892294],
    "Sogʻliq (psixolog)": [1427892294],
    "Boshqa": [1427892294],
}
ADMIN_IDS = set(sum(CATEGORY_ADMINS.values(), []))

# Komitet chat
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
        cur.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            chat_id INTEGER PRIMARY KEY
        )
        """)
        conn.commit()

init_db()
init_channels_db()

# ================== DB FUNKSIYALARI ==================
def save_case(case):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cases (user_id, user_name, created_at, full_name, address, category, description, phone, urgency, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            case.get('user_id'), case.get('user_name'), int(time.time()),
            case.get('full_name'), case.get('address'), case.get('category'),
            case.get('description'), case.get('phone'), case.get('urgency'),
            'new'
        ))
        conn.commit()
        return cur.lastrowid

def get_case(case_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, user_id, user_name, created_at, full_name, address, category, description, phone, urgency, status, committee_note
            FROM cases WHERE id = ?
        """, (case_id,))
        row = cur.fetchone()
        if not row:
            return None
        keys = ["id","user_id","user_name","created_at","full_name","address","category","description","phone","urgency","status","committee_note"]
        return dict(zip(keys, row))

def update_case_status(case_id, status, committee_note=None):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        if committee_note is not None:
            cur.execute("UPDATE cases SET status = ?, committee_note = ? WHERE id = ?", (status, committee_note, case_id))
        else:
            cur.execute("UPDATE cases SET status = ? WHERE id = ?", (status, case_id))
        conn.commit()

# ================== CHANNELS DB FUNKSIYALARI ==================
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
        for adm in admins:
            if getattr(adm, "user", None) and getattr(adm.user, "id", None) == bot_id:
                return True
    except Exception as e:
        logger.debug(f"is_bot_admin_in_chat({chat_id}) error: {e}")
    return False

# ================== USER FLOW ==================
USER_FLOW = {}
REPORT_STEPS = ['full_name', 'address', 'category', 'description', 'phone', 'urgency']
CATEGORY_OPTIONS = list(CATEGORY_ADMINS.keys())
URGENCY_OPTIONS = ['Past', 'Oʻrta', 'Yuqori (shoshilinch)']

# ================== KOMITET XABAR ==================
def notify_committee(case_id):
    case = get_case(case_id)
    if not case:
        logger.warning(f"Case {case_id} topilmadi")
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

    # Kategoriya adminlariga yuborish
    for aid in CATEGORY_ADMINS.get(case.get('category'), []):
        try:
            bot.send_message(aid, text, reply_markup=kb)
        except Exception as e:
            logger.exception(f"notify_committee adminga yuborishda xato: {e}")

    # Psixologga jo'natish
    if case.get('category') == "Sogʻliq (psixolog)":
        try:
            bot.send_message(ADMIN_FOR_PSY_ID, text, reply_markup=kb)
        except Exception as e:
            logger.exception(f"notify_committee psixologga yuborishda xato: {e}")

# ================== START HANDLER ==================
@bot.message_handler(commands=['start'])
def start_handler(message):
    uid = message.from_user.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    if uid == NEWS_ADMIN_ID:
        markup.add("📝 Yangi post qo‘shish")
        bot.send_message(uid, "Assalomu alaykum! Siz yangilik yuborishingiz mumkin.", reply_markup=markup)
        return

    if uid == SUPER_ADMIN_ID:
        markup.add("📊 Statistika")
        bot.send_message(uid, "👑 Assalomu alaykum, Super Admin!", reply_markup=markup)
        return

    markup.add("✍️ Murojaat yuborish")
    bot.send_message(uid,
                     "👋 Salom! Men *Mahalla yordam botiman*.\n\nMuammoni komitetga yuborishingiz mumkin.",
                     parse_mode="Markdown",
                     reply_markup=markup)

# ================== Super Admin Statistika ==================
@bot.message_handler(func=lambda m: m.from_user.id == SUPER_ADMIN_ID and m.text == "📊 Statistika")
def super_admin_stats(message):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM cases")
            total_cases = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM cases WHERE status='resolved'")
            resolved_cases = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM cases WHERE status='new'")
            new_cases = cur.fetchone()[0]

        text = (
            f"📊 Statistika:\n"
            f"🔹 Umumiy murojaatlar: {total_cases}\n"
            f"✅ Hal qilingan: {resolved_cases}\n"
            f"🆕 Yangi: {new_cases}"
        )
        bot.send_message(message.chat.id, text)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Statistikani olishda xato: {e}")

# ================== FOYDALANUVCHIGA XABAR ==================
def send_msg_to_user(message, case_id, is_psy=False):
    case = get_case(case_id)
    if not case:
        bot.send_message(message.chat.id, "❌ Case topilmadi")
        return
    try:
        bot.send_message(case['user_id'], f"📣 {'Psixolog' if is_psy else 'Admin'} xabari:\n\n{message.text}")
        bot.send_message(message.chat.id, "✅ Xabar foydalanuvchiga yuborildi")
        if is_psy:
            bot.send_message(ADMIN_FOR_PSY_ID, f"💡 Psixolog foydalanuvchiga javob yozdi (ID: {case_id})")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Xabar yuborishda xato: {e}")

# ================== CALLBACK HANDLER ==================
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

        if action == "assign_psy":
            bot.answer_callback_query(call_id, "📌 Psixologga yuborildi")
            psy_text = (
                f"📌 Sizga yangi murojaat tayinlandi (ID: {case_id})\n\n"
                f"👤 F.O.: {case.get('full_name')}\n"
                f"📍 Manzil: {case.get('address')}\n"
                f"📂 Toifa: {case.get('category')}\n"
                f"📞 Tel: {case.get('phone')}\n"
                f"⚡ Shoshilinchlik: {case.get('urgency')}\n\n"
                f"📝 Ta'rif:\n{case.get('description')}\n\n"
                f"👤 Foydalanuvchi: @{case.get('user_name') or case.get('user_id')}"
            )
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("✉️ Foydalanuvchiga yozish", callback_data=f"msg_user_psy|{case_id}"))
            bot.send_message(ADMIN_FOR_PSY_ID, psy_text, reply_markup=kb)
            bot.send_message(caller_id, "✅ Psixologga yuborildi")
            return

        if action == "mark_resolved":
            update_case_status(case_id, "resolved")
            bot.answer_callback_query(call_id, "✅ Hal qilindi deb belgilandi")
            return

        if action == "msg_user":
            bot.answer_callback_query(call_id, "✍️ Foydalanuvchiga yozish")
            msg = bot.send_message(caller_id, f"Foydalanuvchi @{case.get('user_name')} ga yuboriladigan xabarni yozing:")
            bot.register_next_step_handler(msg, send_msg_to_user, case_id)
            return

        if action == "msg_user_psy":
            bot.answer_callback_query(call_id, "✍️ Foydalanuvchiga psixolog xabari")
            msg = bot.send_message(caller_id, f"Foydalanuvchi @{case.get('user_name')} ga yuboriladigan psixolog xabarini yozing:")
            bot.register_next_step_handler(msg, send_msg_to_user, case_id, is_psy=True)
            return

# ================== USER MUROJAATLARI ==================
@bot.message_handler(func=lambda m: m.text == "✍️ Murojaat yuborish")
def start_report(message):
    uid = message.from_user.id
    if uid in ADMIN_IDS or uid in [SUPER_ADMIN_ID, ADMIN_FOR_PSY_ID, NEWS_ADMIN_ID]:
        bot.send_message(uid, "❌ Siz murojaat yubora olmaysiz.")
        return
    USER_FLOW[uid] = {'step': 0, 'data': {'user_id': uid, 'user_name': message.from_user.username or message.from_user.first_name}}
    bot.send_message(uid, "Iltimos, to‘liq ismingizni kiriting:")

@bot.message_handler(func=lambda m: m.from_user.id in USER_FLOW)
def report_flow(message):
    uid = message.from_user.id
    flow = USER_FLOW.get(uid)
    if not flow:
        return
    step_idx = flow['step']
    text = message.text.strip()
    key = REPORT_STEPS[step_idx]

    if key == 'full_name':
        flow['data']['full_name'] = text
        flow['step'] += 1
        bot.send_message(uid, "📍 Manzilingizni kiriting:")
        return

    if key == 'address':
        flow['data']['address'] = text
        flow['step'] += 1
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for c in CATEGORY_OPTIONS:
            kb.add(c)
        bot.send_message(uid, "📂 Muammo toifasini tanlang:", reply_markup=kb)
        return

    if key == 'category':
        if text not in CATEGORY_OPTIONS:
            bot.send_message(uid, "❌ Iltimos, toifalardan birini tanlang.")
            return
        flow['data']['category'] = text
        flow['step'] += 1
        bot.send_message(uid, "📝 Muammo tafsilotlarini yozing:", reply_markup=types.ReplyKeyboardRemove())
        return

    if key == 'description':
        flow['data']['description'] = text
        flow['step'] += 1
        bot.send_message(uid, "📞 Telefon raqamingizni yozing:")
        return

    if key == 'phone':
        flow['data']['phone'] = text
        flow['step'] += 1
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for u in URGENCY_OPTIONS:
            kb.add(u)
        bot.send_message(uid, "⚡ Shoshilinchlik darajasini tanlang:", reply_markup=kb)
        return

    if key == 'urgency':
        if text not in URGENCY_OPTIONS:
            bot.send_message(uid, "❌ Iltimos, shoshilinchlik darajasini tugmalardan tanlang.")
            return
        flow['data']['urgency'] = text
        case_id = save_case(flow['data'])
        bot.send_message(uid, f"✅ Rahmat. Xabaringiz qabul qilindi. ID: #{case_id}", reply_markup=types.ReplyKeyboardRemove())
        notify_committee(case_id)
        USER_FLOW.pop(uid, None)
        return

# ================== CHANNEL REGISTRATION HANDLERS ==================
# 1) /addchannel - admin shu kanal ichida yozsa chatni qo'shadi; yoki private-da /addchannel yozsa ko'rsatma beradi
@bot.message_handler(commands=['addchannel'])
def add_channel_cmd(message):
    if message.from_user.id != NEWS_ADMIN_ID:
        bot.reply_to(message, "❌ Ruxsat yo'q.")
        return

    # Agar bu buyruq kanal/guruh ichida berilgan bo'lsa -> qo'shish
    if message.chat.type in ["group", "supergroup", "channel"]:
        add_channel_to_db(message.chat.id)
        bot.reply_to(message, f"✅ Kanal/guruh ro'yxatga qo'shildi: {message.chat.id}")
        return

    # Aks holda ko'rsatma
    bot.reply_to(message, "Kanalni qo'shish uchun ikkita usul bor:\n"
                          "1) Kanal ichida admin sifatida /addchannel buyrug'ini yozing.\n"
                          "2) Kanalning istalgan xabarini menga (botga) **forward** qiling — shunda men kanalni ro'yxatga qo'shaman.")

# 2) Agar NEWS_ADMIN_ID kanal xabarini buferga yuborsa -> avtomatik qo'shamiz
@bot.message_handler(func=lambda m: getattr(m, "forward_from_chat", None) is not None)
def handle_forwarded(m):
    if m.from_user.id != NEWS_ADMIN_ID:
        return
    fchat = m.forward_from_chat
    if not fchat:
        return
    add_channel_to_db(fchat.id)
    bot.reply_to(m, f"✅ Kanal/guruh ro'yxatga qo'shildi: {fchat.id}")

# /delchannel - o'chirish (kanalda yozilsa o'sha kanal, yoki private-da /delchannel <id>)
@bot.message_handler(commands=['delchannel'])
def del_channel_cmd(message):
    if message.from_user.id != NEWS_ADMIN_ID:
        bot.reply_to(message, "❌ Ruxsat yo'q.")
        return
    parts = message.text.strip().split()
    # agar kanal ichida yozilgan bo'lsa
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

# /listchannels - ro'yxatni ko'rish
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

# ================== NEWS_ADMIN POST (HAMMASIGA BIRDEK) ==================
@bot.message_handler(func=lambda m: m.from_user.id == NEWS_ADMIN_ID and m.text == "📝 Yangi post qo‘shish")
def admin_post_start(message):
    msg = bot.send_message(NEWS_ADMIN_ID, "📝 Post matnini yozing yoki rasm yuboring (men ro'yxatdagi HAMMA kanallarga yuboraman):")
    bot.register_next_step_handler(msg, admin_post_send_all)

def admin_post_send_all(message):
    if message.from_user.id != NEWS_ADMIN_ID:
        return

    channels = get_all_channels_from_db()
    if not channels:
        bot.send_message(NEWS_ADMIN_ID, "❌ Ro'yxatda kanal yo'q. Iltimos /addchannel bilan kanal qo'shing.")
        return

    successful = []
    removed = []
    errors = []

    for chat_id in channels:
        # avval bot adminligini tekshiramiz
        if not is_bot_admin_in_chat(chat_id):
            # agar bot admin bo'lmasa, ro'yxatdan olib tashlaymiz
            remove_channel_from_db(chat_id)
            removed.append(chat_id)
            continue
        try:
            if message.content_type == 'text':
                bot.send_message(chat_id, message.text)
            elif message.content_type == 'photo':
                caption = message.caption or ""
                photo_file_id = message.photo[-1].file_id
                bot.send_photo(chat_id, photo_file_id, caption=caption)
            else:
                # boshqa media turlarini kerak bo'lsa qo'shish mumkin
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

# ================== RUN BOT ==================
if __name__ == "__main__":
    print("🤖 Bot ishga tushdi...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
