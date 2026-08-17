"""
Main Application Entrypoint for Freelance AI Financial Engine.
Initializes Database, Telegram Bot, Handlers, and Automated Schedulers.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings
from database import get_storage
from reporter import monthly_reporter
from bot import (
    cmd_start,
    cmd_help,
    cmd_status,
    cmd_report,
    cmd_buffer,
    cmd_draw_buffer,
    cmd_history,
    cmd_settings,
    cmd_set_param,
    cmd_invoice,
    cmd_unpaid,
    cmd_pay_invoice,
    cmd_remind_invoice,
    cmd_export,
    cmd_export_pdf,
    cmd_goals,
    cmd_add_goal,
    cmd_delete_goal,
    cmd_subscriptions,
    cmd_add_subscription,
    cmd_delete_subscription,
    cmd_advisor,
    cmd_health_score,
    cmd_quote,
    cmd_quotes,
    cmd_termin,
    cmd_termins,
    cmd_affordability_radar,
    cmd_forecast,
    cmd_kurs,
    cmd_convert,
    cmd_pajak,
    cmd_export_spt,
    cmd_rate,
    handle_photo,
    handle_voice,
    handle_text_message,
    handle_callback_query,
    scheduled_daily_checkin,
    scheduled_subscription_reminder,
    global_error_handler,
)

# Configure structured logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("FreelanceFinancialEngine")


async def scheduled_monthly_report(app: Application) -> None:
    """Scheduled task that pushes monthly reports to authorized users."""
    logger.info("Executing scheduled end-of-month financial report...")
    storage = get_storage()
    users = settings.allowed_users
    
    if not users:
        logger.info("No specific allowed user IDs configured for scheduled push.")
        return

    for uid in users:
        try:
            report_text, chart_bytes = await monthly_reporter.generate_report_for_user(user_id=uid)
            if chart_bytes:
                import io
                await app.bot.send_photo(
                    chat_id=uid,
                    photo=io.BytesIO(chart_bytes),
                    caption=f"🔔 *Laporan Keuangan Otomatis Akhir Bulan*\n\n{report_text}",
                    parse_mode="Markdown",
                )
            else:
                await app.bot.send_message(
                    chat_id=uid,
                    text=f"🔔 *Laporan Keuangan Otomatis Akhir Bulan*\n\n{report_text}",
                    parse_mode="Markdown",
                )
            logger.info("Sent scheduled monthly report to user_id: %s", uid)
        except Exception as e:
            logger.error("Failed to send scheduled report to user_id %s: %s", uid, e)


def create_bot_application() -> Application:
    """Build and configure the Telegram Bot Application with proxy support for PythonAnywhere."""
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning(
            "TELEGRAM_BOT_TOKEN is empty. Set it in .env file before running in production."
        )

    # Auto-detect PythonAnywhere free tier proxy
    if "PYTHONANYWHERE_DOMAIN" in os.environ or "PYTHONANYWHERE_SITE" in os.environ or os.path.exists("/var/www"):
        os.environ.setdefault("HTTP_PROXY", "http://proxy.server:3128")
        os.environ.setdefault("HTTPS_PROXY", "http://proxy.server:3128")
        os.environ.setdefault("http_proxy", "http://proxy.server:3128")
        os.environ.setdefault("https_proxy", "http://proxy.server:3128")

    builder = Application.builder().token(settings.TELEGRAM_BOT_TOKEN or "DUMMY_TOKEN_FOR_TESTING")

    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy_url:
        try:
            builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)
            logger.info("Configured Telegram Bot with proxy: %s", proxy_url)
        except Exception as e:
            logger.warning("Could not set proxy on builder: %s", e)

    app = builder.build()

    # 1. Core Command Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("buffer", cmd_buffer))
    app.add_handler(CommandHandler("draw_buffer", cmd_draw_buffer))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("settings", cmd_settings))

    # Productivity Commands: Invoices & Export
    app.add_handler(CommandHandler("invoice", cmd_invoice))
    app.add_handler(CommandHandler("invoices", cmd_unpaid))
    app.add_handler(CommandHandler("unpaid", cmd_unpaid))
    app.add_handler(CommandHandler("pay_invoice", cmd_pay_invoice))
    app.add_handler(CommandHandler("remind_invoice", cmd_remind_invoice))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("export_pdf", cmd_export_pdf))
    app.add_handler(CommandHandler("pdf", cmd_export_pdf))

    # Goals & Wishlist Auto-Split Commands
    app.add_handler(CommandHandler("goals", cmd_goals))
    app.add_handler(CommandHandler("wishlist", cmd_goals))
    app.add_handler(CommandHandler("add_goal", cmd_add_goal))
    app.add_handler(CommandHandler("delete_goal", cmd_delete_goal))

    # Recurring Subscriptions Tracker Commands
    app.add_handler(CommandHandler("subscriptions", cmd_subscriptions))
    app.add_handler(CommandHandler("subs", cmd_subscriptions))
    app.add_handler(CommandHandler("tagihan", cmd_subscriptions))
    app.add_handler(CommandHandler("add_sub", cmd_add_subscription))
    app.add_handler(CommandHandler("delete_sub", cmd_delete_subscription))

    # AI Financial Advisor & Health Score Commands
    app.add_handler(CommandHandler("advisor", cmd_advisor))
    app.add_handler(CommandHandler("coach", cmd_advisor))
    app.add_handler(CommandHandler("health", cmd_health_score))
    app.add_handler(CommandHandler("score", cmd_health_score))

    # Quotations & Surat Penawaran Harga (SPH) Commands
    app.add_handler(CommandHandler("quote", cmd_quote))
    app.add_handler(CommandHandler("penawaran", cmd_quote))
    app.add_handler(CommandHandler("sph", cmd_quote))
    app.add_handler(CommandHandler("quotes", cmd_quotes))

    # Project Termins & Milestones Commands
    app.add_handler(CommandHandler("termin", cmd_termin))
    app.add_handler(CommandHandler("milestone", cmd_termin))
    app.add_handler(CommandHandler("dp", cmd_termin))
    app.add_handler(CommandHandler("termins", cmd_termins))

    # Instant Affordability Radar ("Boleh Beli Nggak?") Commands
    app.add_handler(CommandHandler("beli", cmd_affordability_radar))
    app.add_handler(CommandHandler("can_i_buy", cmd_affordability_radar))
    app.add_handler(CommandHandler("afford", cmd_affordability_radar))

    # 90-Day AI Cashflow Forecasting Commands
    app.add_handler(CommandHandler("forecast", cmd_forecast))
    app.add_handler(CommandHandler("proyeksi", cmd_forecast))

    # Multi-Currency & Realtime Kurs Commands
    app.add_handler(CommandHandler("kurs", cmd_kurs))
    app.add_handler(CommandHandler("convert", cmd_convert))
    app.add_handler(CommandHandler("fx", cmd_convert))

    # AI Tax Estimator & SPT Tahunan Form 1770 Commands
    app.add_handler(CommandHandler("pajak", cmd_pajak))
    app.add_handler(CommandHandler("tax", cmd_pajak))
    app.add_handler(CommandHandler("spt", cmd_pajak))
    app.add_handler(CommandHandler("export_spt", cmd_export_spt))

    # Hourly Rate & Project Pricing Calculator Commands
    app.add_handler(CommandHandler("rate", cmd_rate))
    app.add_handler(CommandHandler("hitung_harga", cmd_rate))
    app.add_handler(CommandHandler("pricing", cmd_rate))
    app.add_handler(CommandHandler("harga", cmd_rate))

    # Setting update commands
    app.add_handler(CommandHandler("set_salary", cmd_set_param))
    app.add_handler(CommandHandler("set_tax", cmd_set_param))
    app.add_handler(CommandHandler("set_needs", cmd_set_param))
    app.add_handler(CommandHandler("set_wants", cmd_set_param))
    app.add_handler(CommandHandler("set_ops", cmd_set_param))
    app.add_handler(CommandHandler("set_name", cmd_set_param))
    app.add_handler(CommandHandler("set_bank", cmd_set_param))

    # 2. Photo OCR Handler
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # 3. Voice Note Audio Handler
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # 4. Text Message / NLP Handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # 5. Callback Query Handler (Inline Buttons)
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # 6. Global Error Handler
    app.add_error_handler(global_error_handler)

    return app


async def main():
    logger.info("🚀 Starting Freelance AI Financial Engine...")

    # 1. Initialize Storage Backend
    storage = get_storage()
    await storage.init_db()
    logger.info("Database initialized successfully.")

    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error(
            "❌ ERROR: TELEGRAM_BOT_TOKEN is not configured! Please set TELEGRAM_BOT_TOKEN in .env."
        )
        sys.exit(1)

    # 2. Build Telegram App
    app = create_bot_application()

    # 3. Setup Scheduler for Monthly Reports, Daily Check-In, & Subscription Reminders
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_monthly_report,
        CronTrigger(
            day="last",
            hour=settings.REPORT_TIME_HOUR,
            minute=settings.REPORT_TIME_MINUTE,
        ),
        args=[app],
    )
    scheduler.add_job(
        scheduled_daily_checkin,
        CronTrigger(
            hour=settings.DAILY_CHECKIN_HOUR,
            minute=settings.DAILY_CHECKIN_MINUTE,
        ),
        args=[app],
    )
    scheduler.add_job(
        scheduled_subscription_reminder,
        CronTrigger(
            hour=9,
            minute=0,
        ),
        args=[app],
    )
    scheduler.start()
    logger.info(
        "Scheduler started. Auto-report scheduled for last day of month at %02d:%02d, Daily Check-In at %02d:%02d, Subscription Reminder at 09:00.",
        settings.REPORT_TIME_HOUR,
        settings.REPORT_TIME_MINUTE,
        settings.DAILY_CHECKIN_HOUR,
        settings.DAILY_CHECKIN_MINUTE,
    )

    # 4. Start Cloud Web Health Check Server (Render / Koyeb / Railway)
    port_env = os.environ.get("PORT", "8000")
    health_server = None
    if port_env:
        try:
            port = int(port_env)
            async def handle_health_ping(reader, writer):
                await reader.read(512)
                body = '{"status":"ok","app":"Asisten Keuangan Bot 24/7"}\n'
                response = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body.encode('utf-8'))}\r\n"
                    "Connection: close\r\n\r\n"
                    f"{body}"
                )
                writer.write(response.encode("utf-8"))
                await writer.drain()
                writer.close()
                await writer.wait_closed()

            health_server = await asyncio.start_server(handle_health_ping, "0.0.0.0", port)
            logger.info("🌐 Web health check server listening on 0.0.0.0:%d for 24/7 cloud hosting.", port)
        except Exception as e:
            logger.warning("Could not start cloud health server on port %s: %s", port_env, e)

    # 5. Start Telegram Bot Polling
    logger.info("🤖 Asisten Keuangan Bot is running and listening for messages...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    # Keep running until interrupted
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down bot...")
    finally:
        if health_server:
            health_server.close()
            await health_server.wait_closed()
        scheduler.shutdown()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        logger.info("Asisten Keuangan shut down cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
