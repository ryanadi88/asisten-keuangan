"""
WSGI entry point for PythonAnywhere 24/7 Webhook hosting.
Receives incoming Telegram updates via HTTPS webhook and processes them asynchronously.
"""

import os
import sys
import asyncio
import logging
from flask import Flask, request, jsonify
from telegram import Update

from config import settings
from database import get_storage
from main import create_bot_application

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AsistenKeuanganWSGI")

app = Flask(__name__)

# Initialize background event loop and Telegram application
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

bot_app = create_bot_application()
try:
    loop.run_until_complete(get_storage().init_db())
    loop.run_until_complete(bot_app.initialize())
except Exception as e:
    logger.error("Initialization error in WSGI: %s", e)


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "ok",
        "app": "Asisten Keuangan Bot",
        "mode": "Telegram Webhook 24/7",
        "timezone": os.environ.get("TIMEZONE", "Asia/Jakarta"),
    })


@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    if request.method == "POST":
        try:
            data = request.get_json(force=True)
            if data:
                update = Update.de_json(data, bot_app.bot)
                loop.run_until_complete(bot_app.process_update(update))
            return "OK", 200
        except Exception as e:
            logger.error("Error processing telegram webhook update: %s", e)
            return "Error", 500
    return "Method Not Allowed", 405


@app.route("/set_webhook", methods=["GET"])
def set_webhook_url():
    """Helper route to register the webhook URL to Telegram API with 1-click."""
    base_url = request.host_url.rstrip("/")
    if base_url.startswith("http://"):
        base_url = "https://" + base_url[7:]

    webhook_target = f"{base_url}/webhook"
    success = loop.run_until_complete(bot_app.bot.set_webhook(url=webhook_target))

    return jsonify({
        "success": success,
        "webhook_url": webhook_target,
        "message": "Webhook berhasil didaftarkan ke Telegram!" if success else "Gagal mendaftarkan webhook.",
    })
