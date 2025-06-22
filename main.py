import os
import hashlib
import sqlite3
import secrets
from datetime import datetime
from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    phone TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT,
                    original_filename TEXT,
                    filetype TEXT,
                    user_id INTEGER,
                    download_token TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )''')
    conn.commit()
    conn.close()


def add_user(user):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, phone) VALUES (?, ?, ?, ?, NULL)",
              (user.id, user.username, user.first_name, user.last_name))
    conn.commit()
    conn.close()


def get_user_phone(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT phone FROM users WHERE user_id=?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else None


def ensure_user_folder(user):
    path = os.path.join(BASE_DIR, str(user.id))
    os.makedirs(path, exist_ok=True)
    return path


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)

    phone = get_user_phone(user.id)
    if not phone:
        kb = [[KeyboardButton("📱 ارسال شماره", request_contact=True)]]
        reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("لطفا برای ادامه شماره تلفن خود را ارسال کنید ", reply_markup=reply_markup)
        return

    kb = [
        ["📁 دریافت تمامی فایل های ذخیره شده", "📊 نمایش وضعیت"],["📤 دریافت آخرین فایل آپلودی"]
    ]
    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("🥳 به ربات سیبیل اپلودر خوش آمدید 🥳", reply_markup=reply_markup)


async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contact = update.message.contact
    if contact and contact.user_id == user.id:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET phone=? WHERE user_id=?", (contact.phone_number, user.id))
        conn.commit()
        conn.close()

        kb = [["📁 دریافت تمامی فایل های ذخیره شده", "📊 نمایش وضعیت"],["📤 دریافت آخرین فایل آپلودی"]]
        reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text("✅ شماره تلفن شما تایید و ذخیره شد حالا میتوانید ادامه دهید ✅", reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ لطفا شماره خودتان را ارسال کنید ❌")


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    phone = get_user_phone(user.id)
    if not phone:
        await update.message.reply_text("❌ لطفا ابتدا شماره خود را ارسال و تایید کنید ❌")
        return

    if update.message.document:
        file = update.message.document
        original_filename = file.file_name
        filetype = file.mime_type
    elif update.message.photo:
        file = update.message.photo[-1]
        original_filename = f"photo_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        filetype = "image"
    elif update.message.video:
        file = update.message.video
        original_filename = file.file_name or f"video_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
        filetype = "video"
    elif update.message.audio:
        file = update.message.audio
        original_filename = file.file_name or f"audio_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp3"
        filetype = "audio"
    else:
        await update.message.reply_text("❌ لطفا فقط عکس، ویدیو، موزیک یا سند ارسال کنید ❌")
        return

    waiting_msg = await update.message.reply_text("⏳ در حال دانلود فایل...", reply_to_message_id=update.message.message_id)

    ext = os.path.splitext(original_filename)[1]
    hashed_name = hashlib.sha256((original_filename + str(user.id) + datetime.now().isoformat()).encode()).hexdigest() + ext
    user_folder = ensure_user_folder(user)
    file_path = os.path.join(user_folder, hashed_name)

    new_file = await file.get_file()
    await new_file.download_to_drive(file_path)

    token = str(secrets.token_urlsafe(32))
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO files (filename, original_filename, filetype, user_id, download_token) VALUES (?, ?, ?, ?, ?)",
              (hashed_name, original_filename, filetype, user.id, token))
    conn.commit()
    conn.close()

    await context.bot.delete_message(update.effective_chat.id, waiting_msg.message_id)
    await update.message.reply_text("✅ فایل ذخیره شد", reply_to_message_id=update.message.message_id)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    phone = get_user_phone(user.id)
    if not phone:
        await update.message.reply_text("❌ لطفا ابتدا شماره خود را ارسال و تایید کنید ❌")
        return

    if update.message.text == "📁 دریافت تمامی فایل های ذخیره شده":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, filename, filetype, original_filename FROM files WHERE user_id=?", (user.id,))
        files = c.fetchall()
        conn.close()

        if not files:
            await update.message.reply_text("❌ هیچ فایلی یافت نشد")
            return

        user_folder = ensure_user_folder(user)
        for file_id, filename, filetype, original_name in files:
            file_path = os.path.join(user_folder, filename)
            if not os.path.exists(file_path):
                await update.message.reply_text(f"فایل {original_name} پیدا نشد.")
                continue

            button_list = [[InlineKeyboardButton("📥 دریافت لینک دانلود", callback_data=f"getlink_{file_id}")]]

            if filetype.endswith("mp4"):
                video_url = f"http://{WEBSERVIECE_IP}/watch/{user.id}/{filename}"
                button_list.append([InlineKeyboardButton("🎬 پخش ویدیو", url=video_url)])

            buttons = InlineKeyboardMarkup(button_list)

            if filetype.startswith("image"):
                await update.message.reply_photo(photo=open(file_path, 'rb'), caption=original_name, reply_markup=buttons)
            elif filetype.startswith("video"):
                await update.message.reply_video(video=open(file_path, 'rb'), caption=original_name, reply_markup=buttons)
            elif filetype.startswith("audio"):
                await update.message.reply_audio(audio=open(file_path, 'rb'), caption=original_name, reply_markup=buttons)
            else:
                await update.message.reply_document(document=open(file_path, 'rb'), caption=original_name, reply_markup=buttons)

    elif update.message.text == "📊 نمایش وضعیت":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT filetype, COUNT(*) FROM files WHERE user_id=? GROUP BY filetype", (user.id,))
        stats = c.fetchall()
        conn.close()

        if not stats:
            await update.message.reply_text("❌ هیچ فایلی یافت نشد")
            return

        msg = "<b>📊 وضعیت آپلودهای شما:</b>\n\n"
        for ftype, count in stats:
            msg += f"<b>{ftype}</b> : <code>{count}</code> فایل\n"
        await update.message.reply_text(msg, parse_mode="HTML")

    elif update.message.text == "📤 دریافت آخرین فایل آپلودی":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, filename, filetype, original_filename FROM files WHERE user_id=? ORDER BY id DESC LIMIT 1", (user.id,))
        last_file = c.fetchone()
        conn.close()

        if not last_file:
            await update.message.reply_text("❌ هنوز هیچ فایلی آپلود نکرده‌اید.")
            return

        file_id, filename, filetype, original_name = last_file
        user_folder = ensure_user_folder(user)
        file_path = os.path.join(user_folder, filename)

        if not os.path.exists(file_path):
            await update.message.reply_text("❌ فایل یافت نشد.")
            return

        button_list = [[InlineKeyboardButton("📤 دریافت لینک دانلود", callback_data=f"getlink_{file_id}")]]

        if filetype.endswith("mp4"):
            video_url = f"http://{WEBSERVIECE_IP}/watch/{user.id}/{filename}"
            button_list.append([InlineKeyboardButton("🎬 پخش ویدیو", url=video_url)])

        reply_markup = InlineKeyboardMarkup(button_list)

        if filetype.startswith("image"):
            await update.message.reply_photo(photo=open(file_path, 'rb'), caption=original_name, reply_markup=reply_markup)
        elif filetype.startswith("video"):
            await update.message.reply_video(video=open(file_path, 'rb'), caption=original_name, reply_markup=reply_markup)
        elif filetype.startswith("audio"):
            await update.message.reply_audio(audio=open(file_path, 'rb'), caption=original_name, reply_markup=reply_markup)
        else:
            await update.message.reply_document(document=open(file_path, 'rb'), caption=original_name, reply_markup=reply_markup)


def generate_and_store_token(file_id):
    token = str(secrets.token_urlsafe(32))
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE files SET download_token=? WHERE id=?", (token, file_id))
    conn.commit()
    conn.close()
    return token

async def download_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    file_id = int(query.data.replace("getlink_", ""))
    token = generate_and_store_token(file_id)

    if token:
        url = f"http://{WEBSERVIECE_IP}/download?token={token}"
        await query.message.reply_text(f"🔗 لینک دانلود (یک‌بار مصرف):\n{url}")

    else:
        await query.message.reply_text("❌ فایل مورد نظر یافت نشد یا متعلق به شما نیست.")


if __name__ == '__main__':
    TOKEN = 'TOKEN'
    BASE_DIR = 'uploads'
    DB_FILE = 'database.db'
    WEBSERVIECE_IP = 'HOST:8002'
    os.makedirs(BASE_DIR, exist_ok=True)
    
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))
    app.add_handler(CallbackQueryHandler(download_link_callback, pattern=r"getlink_\d+"))

    print("Bot is running...")
    app.run_polling()
