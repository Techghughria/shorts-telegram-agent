# Shorts Telegram Agent — Local Linux setup

This repository runs a Telegram bot locally on your computer. It uses OpenAI to create original Shorts metadata and scripts, accepts your own video footage and an AI-generated or licensed music file, renders a vertical preview with FFmpeg, and uploads to YouTube only after you approve it in Telegram.

## What it does

- `/generate <idea>`: creates a title, description, tags, hook, voiceover script, shot list, and an original music-generation prompt.
- `/music`: explains how to register an AI-generated or properly licensed audio track.
- Send an MP4: renders a 720×1280 preview using the latest draft and latest registered music track.
- Approve/Reject buttons: only an explicit approval starts YouTube upload.
- `/status`, `/pending`, `/ideas`, and `/help`.

**Important:** OpenAI creates text and a music prompt; it does not create the finished video footage or music audio in this bot. Use a separate music-generation provider or a track whose licence allows your intended YouTube use. AI-generated music is not automatically copyright-free.

## Requirements

- Linux (Ubuntu/Debian instructions below), Python 3.10+, FFmpeg.
- Telegram bot token from BotFather.
- OpenAI API key with API billing/access enabled.
- For actual YouTube uploads: Google Cloud project, YouTube Data API v3 enabled, and an OAuth authorized-user token with the `youtube.upload` scope for your own channel.

## Install on Ubuntu/Debian

1. Clone the repository and enter it:
   ```bash
   git clone https://github.com/Techghughria/shorts-telegram-agent.git
   cd shorts-telegram-agent
   ```
2. Install system packages:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-venv python3-pip ffmpeg
   ```
3. Run the setup script:
   ```bash
   chmod +x setup.sh run.sh
   ./setup.sh
   ```
4. Edit `.env` and add your Telegram and OpenAI values. Keep this file private; it is ignored by Git:
   ```bash
   nano .env
   ```
5. Start the bot:
   ```bash
   ./run.sh
   ```
6. Open your bot in Telegram, send `/start`, then try `/generate a 30-second Hindi short about...`.

## Local .env settings

Required for bot startup and AI generation:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ADMIN_CHAT_ID` — your numeric Telegram user/chat ID (private chat with the bot).
- `OPENAI_API_KEY`

Optional:
- `OPENAI_MODEL` defaults to `gpt-6.1-sol`.
- `YOUTUBE_TOKEN_JSON` — paste the complete OAuth authorized-user JSON on one line to enable upload.
- `YOUTUBE_API_KEY` — only used for `/ideas`.
- `YOUTUBE_PRIVACY` defaults to `private`; keep it private while testing.
- `DATA_DIR` defaults to `./data`.

Do not paste API keys, bot tokens, OAuth tokens, or client secrets into GitHub or chat messages.

## Music workflow

After `/generate <idea>`, use the returned music prompt in a separate music service. Send the resulting MP3/WAV/M4A file to the bot with one of these captions:

```text
AI | provider | licence terms URL/details | RIGHTS_CONFIRMED
LICENSED | source | licence/receipt details | RIGHTS_CONFIRMED
```

The final marker is your declaration that you checked the terms. The bot cannot independently verify the licence.

## Video workflow

Send an MP4 after generating a draft. The bot uses the latest AI draft unless you provide a caption with the title on the first line and description on following lines. It mixes the latest registered music track, renders a vertical preview, and sends it back with Approve/Reject buttons. Only Approve triggers YouTube upload.

Telegram Bot API file downloads are limited; this starter defaults to 19 MB. For larger media, use a local Telegram Bot API server or another intake method rather than assuming larger files will download.

## YouTube OAuth setup

Enable YouTube Data API v3 in Google Cloud, create OAuth credentials for a desktop app, and authorize the channel you own with the `youtube.upload` scope. Store the resulting authorized-user JSON in `YOUTUBE_TOKEN_JSON` in your local `.env`. An API key by itself cannot upload videos.

## Troubleshooting

- `Conflict: terminated by other getUpdates request`: stop any other copy of this bot using the same token.
- `ffmpeg not found`: install FFmpeg with `sudo apt install ffmpeg`.
- OpenAI authentication/model errors: verify the API key, account API access/billing, and the model configured in `.env`.
- YouTube upload errors: verify OAuth JSON, refresh token, YouTube Data API v3, and the `youtube.upload` scope.

This is a local testing setup. No Render or Oracle deployment is required.
