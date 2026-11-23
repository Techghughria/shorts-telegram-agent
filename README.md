# Shorts Telegram Agent — OpenAI content + music + YouTube approval

Cloud Telegram worker. OpenAI generates original Shorts metadata, scripts, shot lists and music-generation prompts. The bot accepts a licensed or externally AI-generated audio file, renders a vertical preview, and waits for Telegram approval before uploading.

## Commands
- /generate <idea>: title, description, tags, hook, voiceover, shot list and original music prompt.
- /music: instructions to add a licensed or AI-generated audio file.
- /ideas: popular YouTube videos in India for research only.
- /status and /pending.

## Music intake
Send audio with caption: AI | provider | licence/terms URL or details | RIGHTS_CONFIRMED
or LICENSED | source | licence/receipt details | RIGHTS_CONFIRMED
OpenAI creates the music prompt, not the audio file. Use a separate music provider or a properly licensed track. AI music is not automatically copyright-free. Rights confirmation is the user's declaration; the bot cannot independently verify licences.

## Video workflow
Run /generate <idea>, create the music track and send it with the music caption, then send an MP4. The bot uses the latest AI draft (or a custom video caption), mixes the latest registered track, renders 720x1280 portrait video, and sends a preview with Approve/Reject. Only Approve triggers YouTube upload. Default privacy is private.

## Render deployment
Create a GitHub repository, then Render > New > Blueprint and connect this repo. The blueprint creates a Background Worker and persistent disk at /var/data. Configure TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID, OPENAI_API_KEY, YOUTUBE_TOKEN_JSON, and optional YOUTUBE_API_KEY. Never commit secrets.

## OpenAI
The model is configured by OPENAI_MODEL. The code uses the OpenAI Python SDK Responses API and expects JSON output. Set a model enabled for your API project. Keep the API key only in Render secrets.

## YouTube OAuth
Enable YouTube Data API v3 in Google Cloud. Create OAuth credentials and obtain an authorized-user token with youtube.upload scope for the channel you control. Put the token JSON in Render's YOUTUBE_TOKEN_JSON secret. An API key alone cannot upload videos.

## Limits and safeguards
Telegram's cloud Bot API getFile download limit is 20 MB; this starter defaults to 19 MB. FFmpeg clips to MAX_SHORT_SECONDS (default 180). The bot is restricted to the configured admin chat/user ID. Keep YOUTUBE_PRIVACY=private until verified. It does not scrape other creators' video/audio. Copyright claims cannot be guaranteed away.
