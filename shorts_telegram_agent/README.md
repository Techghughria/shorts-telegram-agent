# Shorts Telegram Agent — Cloud deployment starter

This repository is a Telegram-controlled YouTube upload worker.

## What works in this starter
- Private Telegram bot restricted to one admin chat/user ID.
- Send an MP4 to the bot with a caption: first line = YouTube title; remaining lines = description.
- Bot stores the video and sends an inline **Approve & upload / Reject** keyboard.
- Upload happens only after the admin presses Approve.
- YouTube upload uses OAuth 2.0 and uploads as `private` by default.
- `/ideas` retrieves popular public YouTube video titles for India via `videos.list(chart=mostPopular)`. It does not download or reuse those videos/audio.
- SQLite job states prevent a second approval from uploading an already processed job.

## Deploy on Render
1. Connect this repository to Render and apply `render.yaml`.
2. Add environment variables: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`, `YOUTUBE_TOKEN_JSON`; optional `YOUTUBE_API_KEY`.
3. Keep the persistent disk mounted at `/var/data`.
4. Deploy and check worker logs.

## YouTube OAuth setup
Create a Google Cloud project, enable YouTube Data API v3, configure OAuth consent, create a Desktop app OAuth client, and generate the token using `scripts/auth_youtube.py`. Never commit client secrets or OAuth tokens to GitHub.

## Telegram workflow
Send an MP4 with a caption:
```
Your YouTube title
Your description goes here.
#Shorts
```
The bot asks for approval. Upload only occurs after pressing **Approve & upload**.

## Important limits and safety
- Telegram cloud Bot API downloads are limited in this starter to 19 MB per video.
- YouTube API uploads require OAuth; an API key alone cannot upload.
- Uploads default to private. Review the result before making it public.
- Never use copyrighted music/video without rights. AI-generated music is not automatically copyright-free; check the provider's licence and monetization terms.
- `/ideas` is research only and does not extract clips/audio.
- This starter is an approval + upload control plane, not yet a full autonomous video-generation engine.