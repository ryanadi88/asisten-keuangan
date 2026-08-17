"""
Middleware and error handler for Telegram Bot.
"""

import logging
import traceback
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

from config import settings

logger = logging.getLogger(__name__)


def restricted(func):
    """Decorator to restrict bot access to whitelisted Telegram User IDs."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user:
            return

        if not settings.is_user_allowed(user.id):
            logger.warning("Unauthorized access attempt by user_id: %s (@%s)", user.id, user.username)
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⛔ Maaf, Anda tidak memiliki izin untuk menggunakan bot ini."
                )
            return

        return await func(update, context, *args, **kwargs)

    return wrapped


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a polite notification to the user if possible."""
    logger.error("Exception while handling an update: %s", context.error, exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        err_msg = (
            "⚠️ Terjadi kesalahan saat memproses permintaan Anda.\n"
            f"Detail error: `{str(context.error)}`\n"
            "Silakan coba sesaat lagi atau periksa data input Anda."
        )
        try:
            await update.effective_message.reply_text(err_msg, parse_mode="Markdown")
        except Exception:
            await update.effective_message.reply_text(err_msg)
