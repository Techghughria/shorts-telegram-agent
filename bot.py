import asyncio, json, logging, os, shutil, sqlite3, subprocess, uuid
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"))
log = logging.getLogger("shorts-agent")
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ADMIN_ID = int(os.environ["TELEGRAM_ADMIN_CHAT_ID"])
DATA = Path(os.getenv("DATA_DIR","./data")).expanduser().resolve()
VIDEO, MUSIC, OUTPUT = DATA/"videos", DATA/"music", DATA/"output"
DB = DATA/"agent.sqlite3"
for p in (DATA, VIDEO, MUSIC, OUTPUT): p.mkdir(parents=True, exist_ok=True)
OPENAI_KEY = os.getenv("OPENAI_API_KEY","")
MODEL = os.getenv("OPENAI_MODEL","gpt-6.1-sol")
YT_TOKEN = os.getenv("YOUTUBE_TOKEN_JSON","")
YT_KEY = os.getenv("YOUTUBE_API_KEY","")
YT_PRIVACY = os.getenv("YOUTUBE_PRIVACY","private")
YT_CATEGORY_ID = os.getenv("YOUTUBE_CATEGORY_ID","22")
MAX_MB = int(os.getenv("MAX_TELEGRAM_DOWNLOAD_MB","19"))
MAX_SECONDS = int(os.getenv("MAX_SHORT_SECONDS","180"))
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    with connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS drafts(id INTEGER PRIMARY KEY,payload TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS music(id INTEGER PRIMARY KEY,file_path TEXT,kind TEXT,provider TEXT,licence TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY,file_path TEXT,title TEXT,description TEXT,tags TEXT,status TEXT DEFAULT 'PENDING',youtube_id TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

def admin(u):
    return bool(u.effective_chat and u.effective_user and u.effective_chat.id==ADMIN_ID and u.effective_user.id==ADMIN_ID)

async def denied(u):
    if u.effective_message: await u.effective_message.reply_text("⛔ Private bot: not authorized.")

def ai_generate(idea):
    if not OPENAI_KEY: raise RuntimeError("OPENAI_API_KEY is missing. Add it to your local .env file.")
    client=OpenAI(api_key=OPENAI_KEY,timeout=60,max_retries=2)
    rsp=client.responses.create(
        model=MODEL,
        instructions=("Create original YouTube Shorts content. Never advise copying other creators' clips or songs. "
        "Return valid JSON with title, description, tags (array), hook, voiceover_script, shot_list (array), "
        "music_prompt, music_direction, language. Title max 100 chars. Music prompt must describe an original "
        "instrumental track for a separate music-generation service; do not claim copyright-free status."),
        input=f"Create one engaging original 20-45 second Short from this idea: {idea}",
        max_output_tokens=1400,
        text={"format":{"type":"json_object"}}
    )
    data=json.loads(rsp.output_text)
    for k in ("title","description","tags","hook","voiceover_script","shot_list","music_prompt","music_direction","language"):
        if k not in data: raise ValueError("AI output missing "+k)
    data["title"]=str(data["title"])[:100]
    data["description"]=str(data["description"])[:4500]
    data["tags"]=[str(x).strip() for x in data["tags"] if str(x).strip()][:15]
    return data

def latest_draft():
    with connect() as c: r=c.execute("SELECT payload FROM drafts ORDER BY id DESC LIMIT 1").fetchone()
    return json.loads(r["payload"]) if r else None

def latest_music():
    with connect() as c: return c.execute("SELECT * FROM music ORDER BY id DESC LIMIT 1").fetchone()

def render(src,out,music):
    if not shutil.which("ffmpeg"): raise RuntimeError("FFmpeg missing in container.")
    cmd=["ffmpeg","-y","-i",str(src)]
    if music:
        cmd += ["-stream_loop","-1","-i",str(music),
          "-vf","scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1",
          "-map","0:v:0","-map","1:a:0"]
    else:
        cmd += ["-vf","scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1",
          "-map","0:v:0","-map","0:a?"]
    cmd += ["-t",str(MAX_SECONDS),"-shortest","-c:v","libx264","-preset","veryfast","-crf","27",
            "-c:a","aac","-b:a","128k","-movflags","+faststart",str(out)]
    subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=900)

def yt_upload(path,title,desc,tags):
    if not YT_TOKEN: raise RuntimeError("YOUTUBE_TOKEN_JSON missing.")
    creds=Credentials.from_authorized_user_info(json.loads(YT_TOKEN),SCOPES)
    if creds.expired and creds.refresh_token: creds.refresh(Request())
    if not creds.valid: raise RuntimeError("YouTube OAuth token invalid; re-authorize.")
    yt=build("youtube","v3",credentials=creds,cache_discovery=False)
    body={"snippet":{"title":title[:100],"description":desc[:5000],"tags":tags[:500],"categoryId":YT_CATEGORY_ID},
          "status":{"privacyStatus":YT_PRIVACY,"selfDeclaredMadeForKids":False}}
    media=MediaFileUpload(path,chunksize=8*1024*1024,resumable=True,mimetype="video/mp4")
    req=yt.videos().insert(part="snippet,status",body=body,media_body=media)
    response=None
    while response is None: _,response=req.next_chunk()
    return response["id"]

async def start(u,ctx):
    if not admin(u): return await denied(u)
    await u.message.reply_text("🤖 Shorts Agent online. Commands: /generate idea, /music, /ideas, /status, /pending, /help. Send MP4 for preview. Approval required before upload. YouTube privacy: "+YT_PRIVACY)

async def help_cmd(u,ctx):
    if not admin(u): return await denied(u)
    await u.message.reply_text(
      "/generate <idea> — OpenAI title, description, tags, script, shot list and music prompt\n"
      "/music — music upload instructions\n/ideas — popular videos in India (research only)\n/status /pending\n\n"
      "Send MP3/WAV with caption:\nAI | provider | licence terms URL/details | RIGHTS_CONFIRMED\n"
      "or LICENSED | source | licence URL/details | RIGHTS_CONFIRMED\n\n"
      "Send MP4 with caption (optional): first line title, remaining lines description. "
      "Without caption, latest AI draft is used. Last added cleared track is mixed into the next Short.")

async def music_help(u,ctx):
    if not admin(u): return await denied(u)
    await u.message.reply_text(
      "Music workflow:\n1. Use /generate <idea> to get a music prompt.\n"
      "2. Generate audio with a separate music service whose terms allow YouTube use, or select a properly licensed track.\n"
      "3. Send MP3/WAV/M4A with caption:\nAI | provider | licence/terms URL or details | RIGHTS_CONFIRMED\n"
      "LICENSED | source | licence/receipt details | RIGHTS_CONFIRMED\n"
      "OpenAI creates the prompt, not the audio file. AI music is not automatically copyright-free. Verify rights and retain proof.")

async def generate(u,ctx):
    if not admin(u): return await denied(u)
    idea=" ".join(ctx.args).strip()
    if not idea: return await u.message.reply_text("Usage: /generate <topic or idea>")
    m=await u.message.reply_text("🧠 OpenAI is preparing your content package...")
    try:
        data=await asyncio.to_thread(ai_generate,idea)
        with connect() as c: c.execute("INSERT INTO drafts(payload) VALUES(?)",(json.dumps(data,ensure_ascii=False),))
        msg=("✨ AI content ready\n\nTITLE\n"+data["title"]+"\n\nDESCRIPTION\n"+data["description"]+
          "\n\nTAGS\n"+" ".join("#"+x.lstrip("#").replace(" ","") for x in data["tags"])+
          "\n\nHOOK\n"+data["hook"]+"\n\nVOICEOVER\n"+data["voiceover_script"]+
          "\n\nSHOT LIST\n"+"\n".join("• "+x for x in data["shot_list"])+
          "\n\nMUSIC PROMPT\n"+data["music_prompt"]+"\n\nMUSIC DIRECTION\n"+data["music_direction"]+
          "\n\nCreate/upload the audio track using /music, then send your footage.")
        await m.edit_text(msg[:4000])
    except Exception as e:
        log.exception("OpenAI generation failed"); await m.edit_text("AI generation failed: "+str(e))

async def status(u,ctx):
    if not admin(u): return await denied(u)
    with connect() as c:
        counts={r["status"]:r["n"] for r in c.execute("SELECT status,COUNT(*) n FROM jobs GROUP BY status")}
        tracks=c.execute("SELECT COUNT(*) n FROM music").fetchone()["n"]
    await u.message.reply_text("🟢 Agent online\n"+("\n".join(f"{k}: {v}" for k,v in counts.items()) or "No video jobs yet.")+f"\nMusic tracks: {tracks}\nYouTube privacy: {YT_PRIVACY}")

async def pending(u,ctx):
    if not admin(u): return await denied(u)
    with connect() as c: rows=c.execute("SELECT id,title,status FROM jobs WHERE status='PENDING' ORDER BY id DESC LIMIT 10").fetchall()
    await u.message.reply_text("\n".join(f"#{r['id']} {r['title']} [{r['status']}]" for r in rows) if rows else "No pending approvals.")

async def ideas(u,ctx):
    if not admin(u): return await denied(u)
    if not YT_KEY: return await u.message.reply_text("Set YOUTUBE_API_KEY in your local .env file to enable /ideas.")
    import requests
    try:
        r=requests.get("https://www.googleapis.com/youtube/v3/videos",
          params={"part":"snippet,statistics","chart":"mostPopular","regionCode":"IN","maxResults":10,"key":YT_KEY},timeout=20)
        r.raise_for_status()
        lines=["📈 Popular YouTube videos in India (research only):"]
        for i,x in enumerate(r.json().get("items",[]),1): lines.append(f"{i}. {x['snippet']['title']} — {x['snippet'].get('channelTitle','')}")
        lines.append("Research signals only; not permission to reuse video or music.")
        await u.message.reply_text("\n".join(lines))
    except Exception as e: await u.message.reply_text("Trend lookup failed: "+str(e))

async def receive_audio(u,ctx):
    if not admin(u): return await denied(u)
    msg=u.message
    media=msg.audio or (msg.document if msg.document and (msg.document.mime_type or "").startswith("audio/") else None)
    if not media: return
    parts=[x.strip() for x in (msg.caption or "").split("|")]
    if len(parts)<4 or parts[0].upper() not in ("AI","LICENSED") or parts[-1].upper()!="RIGHTS_CONFIRMED":
        return await msg.reply_text("Caption required:\nAI | provider | licence terms details | RIGHTS_CONFIRMED\nor LICENSED | source | licence details | RIGHTS_CONFIRMED")
    if not parts[1] or not " ".join(parts[2:-1]).strip(): return await msg.reply_text("Provider/source and licence details are required.")
    if media.file_size and media.file_size>MAX_MB*1024*1024: return await msg.reply_text(f"Audio exceeds {MAX_MB} MB Telegram download limit.")
    try:
        f=await ctx.bot.get_file(media.file_id)
        ext=Path(getattr(media,"file_name","") or "track.mp3").suffix or ".mp3"
        path=MUSIC/f"music_{uuid.uuid4().hex[:10]}{ext}"
        await f.download_to_drive(custom_path=path)
        with connect() as c: c.execute("INSERT INTO music(file_path,kind,provider,licence) VALUES(?,?,?,?)",
          (str(path),parts[0].upper(),parts[1]," | ".join(parts[2:-1])))
        await msg.reply_text("🎵 Track saved as the current music track. It will be used for the next video. Licence confirmation is your declaration.")
    except Exception as e:
        log.exception("Audio intake failed"); await msg.reply_text("Could not save audio: "+str(e))

async def receive_video(u,ctx):
    if not admin(u): return await denied(u)
    msg=u.message
    media=msg.video or (msg.document if msg.document and (msg.document.mime_type or "").startswith("video/") else None)
    if not media: return
    if media.file_size and media.file_size>MAX_MB*1024*1024:
        return await msg.reply_text(f"Video exceeds {MAX_MB} MB Telegram cloud download limit in this starter.")
    source=VIDEO/f"source_{uuid.uuid4().hex[:10]}.mp4"
    try:
        f=await ctx.bot.get_file(media.file_id); await f.download_to_drive(custom_path=source)
        draft=latest_draft(); lines=(msg.caption or "").strip().splitlines()
        if lines:
            title=lines[0][:100]; desc="\n".join(lines[1:]).strip() or (draft or {}).get("description","")
            tags=(draft or {}).get("tags",[])
        elif draft: title,desc,tags=draft["title"],draft["description"],draft["tags"]
        else:
            source.unlink(missing_ok=True)
            return await msg.reply_text("Run /generate <idea> first or send a caption with title on line 1 and description below.")
        if not title or not desc:
            source.unlink(missing_ok=True); return await msg.reply_text("Title and description are required.")
        track=latest_music(); out=OUTPUT/f"short_{uuid.uuid4().hex[:10]}.mp4"
        await msg.reply_text("🎞️ Rendering vertical preview...")
        await asyncio.to_thread(render,source,out,Path(track["file_path"]) if track else None)
        with connect() as c:
            cur=c.execute("INSERT INTO jobs(file_path,title,description,tags,status) VALUES(?,?,?,?,'PENDING')",
              (str(out),title,desc,json.dumps(tags,ensure_ascii=False))); job=cur.lastrowid
        music_label=(track["kind"]+" — "+track["provider"]) if track else "Original video audio"
        keyboard=InlineKeyboardMarkup([[
          InlineKeyboardButton("✅ Approve & upload",callback_data=f"approve:{job}"),
          InlineKeyboardButton("❌ Reject",callback_data=f"reject:{job}")]])
        cap=f"🎬 REVIEW REQUIRED #{job}\nTitle: {title}\nMusic: {music_label}\nPrivacy: {YT_PRIVACY}\n\n{desc}"
        with out.open("rb") as file:
            await ctx.bot.send_video(chat_id=ADMIN_ID,video=file,caption=cap[:1024],reply_markup=keyboard,supports_streaming=True)
    except Exception as e:
        log.exception("Video pipeline failed"); await msg.reply_text("Video processing failed: "+str(e))

async def approval(u,ctx):
    q=u.callback_query
    if not admin(u): return await q.answer("Not authorized",show_alert=True)
    await q.answer()
    action,jid=q.data.split(":"); jid=int(jid)
    with connect() as c:
        row=c.execute("SELECT * FROM jobs WHERE id=?",(jid,)).fetchone()
        if not row: return await q.edit_message_caption(caption="Job not found.")
        if row["status"]!="PENDING": return await q.edit_message_caption(caption="Already processed: "+row["status"])
        if action=="reject":
            c.execute("UPDATE jobs SET status='REJECTED' WHERE id=?",(jid,))
            Path(row["file_path"]).unlink(missing_ok=True)
            return await q.edit_message_caption(caption=f"❌ Job #{jid} rejected.")
        c.execute("UPDATE jobs SET status='UPLOADING' WHERE id=?",(jid,))
    await q.edit_message_caption(caption=f"⏳ Approved. Uploading as {YT_PRIVACY}...")
    try:
        vid=await asyncio.to_thread(yt_upload,row["file_path"],row["title"],row["description"],json.loads(row["tags"]))
        with connect() as c: c.execute("UPDATE jobs SET status='UPLOADED',youtube_id=? WHERE id=?",(vid,jid))
        await ctx.bot.send_message(ADMIN_ID,f"✅ Uploaded: https://www.youtube.com/watch?v={vid}\nPrivacy: {YT_PRIVACY}")
        Path(row["file_path"]).unlink(missing_ok=True)
    except Exception as e:
        log.exception("YouTube upload failed")
        with connect() as c: c.execute("UPDATE jobs SET status='UPLOAD_FAILED' WHERE id=?",(jid,))
        await ctx.bot.send_message(ADMIN_ID,"⚠️ Upload failed: "+str(e))

def main():
    init_db()
    app=Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("help",help_cmd))
    app.add_handler(CommandHandler("music",music_help))
    app.add_handler(CommandHandler("generate",generate))
    app.add_handler(CommandHandler("status",status))
    app.add_handler(CommandHandler("pending",pending))
    app.add_handler(CommandHandler("ideas",ideas))
    app.add_handler(CallbackQueryHandler(approval,pattern=r"^(approve|reject):\d+$"))
    app.add_handler(MessageHandler(filters.AUDIO|filters.Document.AUDIO,receive_audio))
    app.add_handler(MessageHandler(filters.VIDEO|filters.Document.VIDEO,receive_video))
    log.info("Starting Telegram worker")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=="__main__": main()
