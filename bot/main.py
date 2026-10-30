# Owner: Dev E
"""Telegram bot for "Is this you?" admission confirmations.

Placeholder: /start <token> acknowledges the link token. Account linking and
confirm/dispute buttons call the backend at API_URL later.
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("apaar-bot")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Welcome to APAAR Integrity Platform. Open the link from your student portal "
            "to connect this chat."
        )
        return
    # TODO(Dev E): POST the token and chat id to the backend to link the student account.
    await update.message.reply_text(
        "Link token received. Account linking is not live yet; you will get a message here "
        "when an institution reports an admission in your name."
    )


def main() -> None:
    load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("TELEGRAM_BOT_TOKEN is not set. Copy the bot block of .env.example into bot/.env.")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    log.info("Bot polling. API_URL=%s", os.environ.get("API_URL", "http://localhost:8000"))
    app.run_polling()


if __name__ == "__main__":
    main()
