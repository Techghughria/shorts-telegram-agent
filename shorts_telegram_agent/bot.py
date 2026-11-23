import asyncio
import json
import logging
import os
import sqlite3
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters,
)
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("shorts-agent")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ADMIN_CHAT_ID = int(os.environ["TELEGRAM_ADMIN_CHAT_ID"])
DATA_DIR = Path(os.getenv("DATA_DIR", "/var/data"))
VIDEO_DIR = DATA_DIR / "videos"
DB_PATH = DATA_DIR / "agent.sqlite3"
YOUTUBE_TOKEN_JSON = os.getenv("YOUTUBE_TOKEN_JSON", "")
YOUTUBE_PRIVACY = os.getenv("YOUTUBE_PRIVACY", "private")
MAX_DOWNLOAD_MB = int(os.getenv("MAX_TELEGRAM_DOWNLOAD_MB", "19"))
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

DATA_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'PENDING',
            youtube_video_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")

def is_admin(update: Update) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    return bool(chat and user and chat.id == ADMIN_CHAT_ID and user.id == ADMIN_CHAT_ID)

async def deny(update: Update):
    if update.effective_message:
        await update.effective_message.reply_text("⛔ This bot is private. You are not authorized.")

def youtube_client():
    if not YOUTUBE_TOKEN_JSON:
        raise RuntimeError("YOUTUBE_TOKEN_JSON is not configured in hosting environment.")
    info = json.loads(YOUTUBE_TOKEN_JSON)
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds.valid:
        raise RuntimeError("YouTube OAuth token is invalid. Re-authorize and update YOUTUBE_TOKEN_JSON.")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)

def upload_to_youtube(path: str, title: str, description: str, tags: list[str]):
    youtube = youtube_client()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:500],
            "categoryId": "10"
        },
        "status": {
            "privacyStatus": YOUTUBE_PRIVACY,
            "selfDeclaredMadeForKids": False
        }
    }
    media = MediaFileUpload(path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    return response["id"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return await deny(update)
    await update.message.reply_text(
        "🤖 Shorts AI Agent is online.\n\n"
        "Send me an MP4 video with a caption:\n"
        "Line 1 = YouTube title\n"
        "Next lines = description\n\n"
        "Commands: /status /pending /ideas /help\n"
        "Every upload requires your Telegram approval. Upload privacy is currently: "
        f"{YOUTUBE_PRIVACY}."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return await deny(update)
    await update.message.reply_text(
        "/start — start bot\n/status — service status\n"
        "/pending — list pending videos\n/ideas — show popular YouTube video ideas\n"
        "/help — this help\n\n"
        "To submit: send a video with caption; first line is title, rest is description. "
        "The bot will ask for approval before uploading."
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return await deny(update)
    with db() as con:
        counts = {r["status"]: r["n"] for r in con.execute(
            "SELECT status, COUNT(*) n FROM jobs GROUP BY status")}
    await update.message.reply_text(
        "🟢 Agent running\n" + "\n".join(f"{k}: {v}" for k, v in counts.items())
        if counts else "🟢 Agent running\nNo videos submitted yet."
    )

async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return await deny(update)
    with db() as con:
        rows = con.execute("SELECT id,title,status FROM jobs WHERE status='PENDING' ORDER BY id DESC LIMIT 10").fetchall()
    if not rows:
        return await update.message.reply_text("No pending approvals.")
    await update.message.reply_text("\n".join(f"#{r['id']} — {r['title']} [{r['status']}]" for r in rows))

async def ideas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return await deny(update)
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        return await update.message.reply_text("Set YOUTUBE_API_KEY in Render environment to enable public trend discovery.")
    import requests
    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet,statistics", "chart": "mostPopular",
                    "regionCode": os.getenv("TREND_REGION", "IN"), "maxResults": 10, "key": key},
            timeout=20,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        lines = ["📈 Popular YouTube videos in India (idea research only):"]
        for i, item in enumerate(items[:10], 1):
            sn = item["snippet"]
            lines.append(f"{i}. {sn['title']} — {sn.get('channelTitle','')}")
        lines.append("\nThis is popularity research, not permission to reuse their videos or audio.")
        await update.message.reply_text("\n".join(lines))
    except Exception as exc:
        log.exception("Trend request failed")
        await update.message.reply_text(f"Trend lookup failed: {exc}")

async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return await deny(update)
    msg = update.message
    video = msg.video
    if not video:
        return
    if video.file_size and video.file_size > MAX_DOWNLOAD_MB * 1024 * 1024:
        return await msg.reply_text(
            f"Video is larger than {MAX_DOWNLOAD_MB} MB. Telegram cloud Bot API download limit applies in this starter. "
            "Use a smaller MP4 or a future object-storage upload flow."
        )
    caption = (msg.caption or "").strip()
    lines = caption.splitlines()
    title = (lines[0].strip() if lines else "")[:100]
    description = "\n".join(lines[1:]).strip()
    if not title:
        return await msg.reply_text("Please add a caption: first line = YouTube title; remaining lines = description.")
    if not description:
        description = " "
    try:
        tg_file = await context.bot.get_file(video.file_id)
        file_path = VIDEO_DIR / f"telegram_{msg.message_id}.mp4"
        await tg_file.download_to_drive(custom_path=file_path)
        with db() as con:
            cur = con.execute(
                "INSERT INTO jobs(file_path,title,description,status) VALUES(?,?,?,'PENDING')",
                (str(file_path), title, description)
            )
            job_id = cur.lastrowid
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve & upload", callback_data=f"approve:{job_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{job_id}")
        ]])
        await msg.reply_text(
            f"🎬 Video ready for review\n\nID: #{job_id}\nTitle: {title}\n"
            f"Description: {description[:700]}\n\n"
            f"Upload privacy: {YOUTUBE_PRIVACY}\nNo upload will happen unless you approve.",
            reply_markup=keyboard
        )
    except Exception as exc:
        log.exception("Could not save submitted video")
        await msg.reply_text(f"Could not process video: {exc}")

async def approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(update):
        await query.answer("Not authorized", show_alert=True)
        return
    await query.answer()
    action, raw_id = query.data.split(":", 1)
    job_id = int(raw_id)
    with db() as con:
        row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return await query.edit_message_text("Job not found.")
        if row["status"] != "PENDING":
            return await query.edit_message_text(f"This job is already {row['status']}.")
        if action == "reject":
            con.execute("UPDATE jobs SET status='REJECTED' WHERE id=? AND status='PENDING'", (job_id,))
            Path(row["file_path"]).unlink(missing_ok=True)
            return await query.edit_message_text(f"❌ Job #{job_id} rejected.")
        if action != "approve":
            return
        con.execute("UPDATE jobs SET status='UPLOADING' WHERE id=? AND status='PENDING'", (job_id,))
    await query.edit_message_text(f"⏳ Job #{job_id}: approved. Uploading to YouTube as {YOUTUBE_PRIVACY}...")
    try:
        video_id = await asyncio.to_thread(
            upload_to_youtube, row["file_path"], row["title"], row["description"], json.loads(row["tags"])
        )
        with db() as con:
            con.execute("UPDATE jobs SET status='UPLOADED', youtube_video_id=? WHERE id=?", (video_id, job_id))
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"✅ Uploaded successfully!\nhttps://www.youtube.com/watch?v={video_id}\n"
                 f"Privacy: {YOUTUBE_PRIVACY}\nTitle: {row['title']}"
        )
        Path(row["file_path"]).unlink(missing_ok=True)
    except Exception as exc:
        log.exception("YouTube upload failed")
        with db() as con:
            con.execute("UPDATE jobs SET status='UPLOAD_FAILED' WHERE id=?", (job_id,))
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"⚠️ Upload failed for #{job_id}: {exc}")

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("pending", pending))
    app.add_handler(CommandHandler("ideas", ideas))
    app.add_handler(CallbackQueryHandler(approval_callback, pattern=r"^(approve|reject):\d+$"))
    app.add_handler(MessageHandler(filters.VIDEO, receive_video))
    log.info("Starting Telegram polling worker")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
