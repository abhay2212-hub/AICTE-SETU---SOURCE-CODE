<!-- Owner: Dev E -->
# bot

Telegram bot for the APAAR Integrity Platform. When an institution reports an admission, the student gets an "Is this you?" message and can confirm or dispute it.

Current state: `/start <token>` acknowledges the link token. Account linking and confirm/dispute buttons are next.

```sh
# bot/.env needs TELEGRAM_BOT_TOKEN, API_URL, TELEGRAM_WEBHOOK_SECRET (see ../.env.example)
uv run python main.py
uv run ruff check .
```

Never log phone numbers, APAAR IDs or message contents.

Owner: Dev E.
