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

# Ensure project root is in sys.path and set as current working directory
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)
os.chdir(project_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_dir, ".env"))

# Auto-detect and configure PythonAnywhere proxy for free accounts
if "PYTHONANYWHERE_DOMAIN" in os.environ or "PYTHONANYWHERE_SITE" in os.environ or os.path.exists("/var/www"):
    os.environ["HTTP_PROXY"] = "http://proxy.server:3128"
    os.environ["HTTPS_PROXY"] = "http://proxy.server:3128"
    os.environ["http_proxy"] = "http://proxy.server:3128"
    os.environ["https_proxy"] = "http://proxy.server:3128"

from config import settings
from database import get_storage
from main import create_bot_application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AsistenKeuanganWSGI")

app = Flask(__name__)

# Initialize background event loop and Telegram application
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

bot_app = None
try:
    bot_app = create_bot_application()
    loop.run_until_complete(get_storage().init_db())
    loop.run_until_complete(bot_app.initialize())
    logger.info("Asisten Keuangan Bot WSGI initialized successfully.")
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
    global bot_app
    if bot_app is None:
        try:
            bot_app = create_bot_application()
            loop.run_until_complete(get_storage().init_db())
            loop.run_until_complete(bot_app.initialize())
        except Exception as e:
            return jsonify({"success": False, "error": str(e), "message": "Failed to initialize bot. Check .env and TELEGRAM_BOT_TOKEN."}), 500

    base_url = request.host_url.rstrip("/")
    if base_url.startswith("http://"):
        base_url = "https://" + base_url[7:]

    webhook_target = f"{base_url}/webhook"
    try:
        success = loop.run_until_complete(bot_app.bot.set_webhook(url=webhook_target))
        return jsonify({
            "success": success,
            "webhook_url": webhook_target,
            "message": "Webhook berhasil didaftarkan ke Telegram!" if success else "Gagal mendaftarkan webhook.",
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/status_db", methods=["GET"])
def check_db_status():
    """Diagnostic route to verify database backend and Google Sheets connection."""
    from database import reset_storage
    reset_storage()

    backend_type = settings.DB_BACKEND
    creds_file = settings.GOOGLE_SHEETS_CREDENTIALS_FILE
    creds_exist = os.path.exists(creds_file) or os.path.exists(os.path.join(project_dir, creds_file))

    details = {
        "configured_backend_in_env": backend_type,
        "credentials_file": creds_file,
        "credentials_file_found": creds_exist,
        "spreadsheet_target": settings.GOOGLE_SPREADSHEET_KEY,
    }

    # Attempt to initialize Google Sheets directly
    try:
        from database.gsheets_db import GoogleSheetsBackend
        gs_backend = GoogleSheetsBackend()
        client = gs_backend._get_client()
        sheet = gs_backend._get_spreadsheet()
        
        details["google_sheets_status"] = "CONNECTED_SUCCESS"
        details["spreadsheet_title"] = sheet.title
        details["spreadsheet_id"] = sheet.id
        details["worksheets_found"] = [ws.title for ws in sheet.worksheets()]
        details["active_backend_class"] = "GoogleSheetsBackend"
    except Exception as e:
        details["google_sheets_status"] = "ERROR_CONNECTING"
        details["error_type"] = type(e).__name__
        details["error_detail"] = str(e)
        details["active_backend_class"] = type(get_storage()).__name__

    return jsonify(details)
