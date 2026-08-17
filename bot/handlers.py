"""
Telegram Bot Handlers: Commands, Photo OCR, Natural Language Parser, Invoices, Exporter, and Callbacks.
"""

import io
import os
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from telegram import Update
from telegram.ext import ContextTypes, Application

from config import settings, format_currency, get_current_month_year
from database import get_storage
from database.models import (
    Transaction,
    TransactionCreate,
    TransactionType,
    Category,
    UserSettings,
    ParsedAIInput,
    BudgetGuardStatus,
    Invoice,
    InvoiceStatus,
    FinancialGoal,
    FinancialGoalCreate,
    Subscription,
    SubscriptionCreate,
    FinancialHealthReport,
    Quotation,
    QuotationCreate,
    QuotationStatus,
    ProjectTermin,
    ProjectTerminCreate,
    ProjectMilestone,
    AffordabilityReport,
    CashflowForecastReport,
    PTKPStatus,
    TaxMethod,
    TaxCalculationReport,
    PricingEstimateReport,
)
from ai import ocr_engine, nlp_parser, gemini_engine, NLPParser
from engine import (
    financial_engine,
    render_progress_bar,
    affordability_radar,
    cashflow_forecaster,
    currency_converter,
    tax_estimator,
    pricing_calculator,
)
from reporter import monthly_reporter
from invoice import invoice_generator, invoice_parser, piutang_tracker
from quotation import quotation_generator, quotation_parser
from termin import termin_tracker
from tools import excel_exporter
from tools.pdf_exporter import pdf_financial_exporter
from bot.keyboards import (
    get_confirmation_keyboard,
    get_category_picker_keyboard,
    get_invoice_action_keyboard,
    get_main_menu_keyboard,
    get_undo_keyboard,
    get_daily_checkin_keyboard,
    get_goals_keyboard,
    get_subscriptions_keyboard,
    get_quotation_action_keyboard,
    get_quotations_keyboard,
    get_termin_action_keyboard,
    get_termins_keyboard,
    get_tax_keyboard,
    get_ptkp_selection_keyboard,
    get_currency_keyboard,
)
from bot.middleware import restricted

logger = logging.getLogger(__name__)


@restricted
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message and onboarding flow."""
    user = update.effective_user
    welcome_text = (
        f"👋 Halo, *{user.first_name}*!\n\n"
        f"Selamat datang di *Asisten Keuangan* 🚀\n"
        f"Sistem all-in-one keuangan otomatis khusus freelancer dengan penghasilan fluktuatif.\n\n"
        f"🌟 *Fitur Unggulan:*\n"
        f"• ⚡ *Multi-Item Batch Entry:* Sekali chat banyak transaksi (`beli buku 30rb, pensil 5rb, warteg 20k`).\n"
        f"• 🎙️ *Voice Note Support:* Cukup kirim pesan suara / voice note untuk mencatat!\n"
        f"• ↩️ *1-Click Undo:* Tombol instan membatalkan/menghapus transaksi jika salah ketik.\n"
        f"• 📊 *Dashboard Visual:* Progress bar anggaran real-time & rekomendasi batas jajan harian.\n"
        f"• 🧾 *PDF Invoice Generator:* Buat invoice PDF resmi dalam hitungan detik (`/invoice`).\n"
        f"• ⏰ *Piutang Klien Tracker:* Pantau tagihan belum lunas & buat pesan tagihan sopan (`/unpaid`).\n"
        f"• 📥 *1-Click Excel Export:* Unduh rekapitulasi data lengkap ke file `.xlsx` (`/export`).\n"
        f"• 📸 *AI Receipt OCR:* Kirim foto struk/invoice untuk pembukuan otomatis.\n"
        f"• 💸 *Dynamic Income Smoothing:* Potong pajak (10%), gaji pokok bulanan, dan simpan surplus di *Buffer Fund*.\n\n"
        f"Gunakan menu di bawah atau ketik `/help` untuk panduan lengkap!"
    )
    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(),
    )


@restricted
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detailed command manual and usage examples."""
    help_text = (
        f"📖 *PANDUAN LENGKAP FREELANCE AI FINANCE*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"1️⃣ *Pembuatan & Pelacakan Invoice:*\n"
        f"• `/invoice` — Buat invoice PDF resmi ke klien\n"
        f"• `/invoices` atau `/unpaid` — Cek tagihan klien belum dibayar\n"
        f"• `Invoice INV-202608-001 lunas` — Chat santai saat klien transfer\n\n"
        f"2️⃣ *Pencatatan Transaksi Conversational:*\n"
        f"• `Masuk fee klien 5jt` (Otomatis potong pajak 10% & alokasi gaji/buffer)\n"
        f"• `Beli kopi starbucks 45rb, beli buku 35rb` (Multi-item batch!)\n"
        f"• 🎙️ *Kirim Voice Note* — Bicara langsung untuk mencatat!\n"
        f"• 📸 *Kirim Foto Struk* untuk ekstraksi AI Vision OCR!\n\n"
        f"3️⃣ *Laporan & Export:*\n"
        f"• `/report` — Laporan bulanan + grafik visual performa keuangan\n"
        f"• `/export` — Unduh file Excel `.xlsx` multi-sheet lengkap\n"
        f"• `/status` — Dashboard budget bar & kuota aman harian\n"
        f"• `/buffer` & `/draw_buffer` — Kelola Buffer Fund saat bulan sepi\n"
        f"• `/settings` — Ubah target gaji, pajak, rekening, dan batas budget"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


@restricted
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick status of budget limits, salary progress, and buffer runway."""
    user_id = update.effective_user.id
    m_y = get_current_month_year()

    health = await financial_engine.get_financial_health(user_id, m_y)
    summary = health["summary"]
    user_settings = health["settings"]
    currency = health["currency"]

    transactions = await get_storage().get_transactions(user_id=user_id, month_year=m_y, limit=500)
    cat_spent = {c.value: 0.0 for c in Category}
    for tx in transactions:
        if tx.type == TransactionType.EXPENSE:
            cat_spent[tx.category.value] = cat_spent.get(tx.category.value, 0.0) + tx.amount

    needs_spent = cat_spent[Category.NEEDS.value]
    wants_spent = cat_spent[Category.WANTS.value]
    ops_spent = cat_spent[Category.OPERATIONAL.value]

    needs_pct = (needs_spent / user_settings.needs_budget * 100.0) if user_settings.needs_budget > 0 else 0.0
    wants_pct = (wants_spent / user_settings.wants_budget * 100.0) if user_settings.wants_budget > 0 else 0.0
    ops_pct = (ops_spent / user_settings.operational_budget * 100.0) if user_settings.operational_budget > 0 else 0.0

    safe_info = await financial_engine.get_daily_safe_spend(user_id, m_y)

    status_text = (
        f"📊 *DASHBOARD STATUS KEUANGAN ({m_y})*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Total Income:* `{format_currency(summary.total_income, currency)}`\n"
        f"💸 *Total Expense:* `{format_currency(summary.total_expense, currency)}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 *Target Gaji Bulanan:*\n"
        f"• `{format_currency(summary.actual_salary_drawn, currency)}` / `{format_currency(user_settings.target_salary, currency)}`\n"
        f"• Progres: {render_progress_bar(health['salary_pct'])}\n\n"
        f"🛡️ *Buffer Runway:* *{health['runway_months']} Bulan Biaya Hidup*\n"
        f"• Saldo Buffer Pool: `{format_currency(summary.buffer_fund_balance, currency)}`\n"
        f"• Status: *{health['health_badge']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 *Pengeluaran vs Batas Anggaran:*\n"
        f"• 🏠 *Needs:* {render_progress_bar(needs_pct)}\n"
        f"  `{format_currency(needs_spent, currency)}` / `{format_currency(user_settings.needs_budget, currency)}`\n"
        f"• ☕ *Wants:* {render_progress_bar(wants_pct)}\n"
        f"  `{format_currency(wants_spent, currency)}` / `{format_currency(user_settings.wants_budget, currency)}`\n"
        f"• 💻 *Ops:* {render_progress_bar(ops_pct)}\n"
        f"  `{format_currency(ops_spent, currency)}` / `{format_currency(user_settings.operational_budget, currency)}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 *Smart Daily Safe-to-Spend:*\n"
        f"• Kuota Aman Harian: *`{format_currency(safe_info['daily_safe_limit'], currency)}` / hari*\n"
        f"• Sisa Hari Bulan Ini: *{safe_info['days_remaining']} hari*\n"
        f"• Pengeluaran Hari Ini: `{format_currency(safe_info['today_spent'], currency)}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 _{health['health_advice']}_"
    )
    await update.message.reply_text(status_text, parse_mode="Markdown")


@restricted
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send full monthly report + visual chart photo."""
    user_id = update.effective_user.id
    processing_msg = await update.message.reply_text("⏳ Sedang mengolah laporan keuangan & merender grafik visual...")

    report_text, chart_bytes = await monthly_reporter.generate_report_for_user(user_id=user_id)

    await processing_msg.delete()

    if chart_bytes:
        await update.message.reply_photo(
            photo=io.BytesIO(chart_bytes),
            caption=report_text,
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(report_text, parse_mode="Markdown")


@restricted
async def cmd_buffer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check buffer fund status and explain smoothing mechanism."""
    user_id = update.effective_user.id
    m_y = get_current_month_year()
    health = await financial_engine.get_financial_health(user_id, m_y)
    summary = health["summary"]
    currency = health["currency"]

    buffer_text = (
        f"🛡️ *INCOME SMOOTHING & BUFFER POOL*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Saldo Buffer Saat Ini:* `{format_currency(summary.buffer_fund_balance, currency)}`\n"
        f"⏳ *Safety Runway:* *{health['runway_months']} Bulan Biaya Hidup*\n"
        f"🎯 *Target Gaji Bulanan:* `{format_currency(summary.target_salary, currency)}`\n\n"
        f"📌 *Cara Kerja Income Smoothing:*\n"
        f"1. Saat dapat fee proyek besar, surplus setelah target gaji otomatis disimpan di Buffer Pool.\n"
        f"2. Saat bulan sepi, Anda dapat menarik gaji pokok dari Buffer Pool agar hidup tetap stabil.\n\n"
        f"👉 Untuk menarik dana gaji saat bulan sepi, gunakan:\n"
        f"`/draw_buffer` (menarik sisa kuota gaji bulan ini)\n"
        f"`/draw_buffer 5000000` (menarik nominal tertentu)"
    )
    await update.message.reply_text(buffer_text, parse_mode="Markdown")


@restricted
async def cmd_draw_buffer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute manual drawdown from buffer fund for lean months."""
    user_id = update.effective_user.id
    args = context.args
    amount = None
    if args and len(args) > 0:
        try:
            amount = float(args[0].replace(".", "").replace(",", "").replace("k", "000").replace("jt", "000000"))
        except ValueError:
            pass

    success, msg = await financial_engine.draw_salary_from_buffer(user_id=user_id, amount=amount)
    await update.message.reply_text(msg, parse_mode="Markdown")


@restricted
async def cmd_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a new client invoice, render PDF, save to DB, and send to user."""
    user_id = update.effective_user.id
    raw_args = " ".join(context.args) if context.args else ""

    if not raw_args.strip():
        # Provide interactive syntax help
        help_msg = (
            "🧾 *PANDUAN MEMBUAT PDF INVOICE*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Gunakan format berikut:\n"
            "`/invoice Klien: [Nama Klien] | Project: [Nama Proyek] | Nominal: [Biaya] | Due: [X hari]`\n\n"
            "📌 *Contoh Penggunaan:*\n"
            "`/invoice Klien: PT Maju Digital | Project: Redesign Website UI | Nominal: 8.5jt | Due: 14 hari`\n\n"
            "👉 *Tips:* Anda juga bisa menambahkan `Email:` dan `Notes:` jika diperlukan."
        )
        await update.message.reply_text(help_msg, parse_mode="Markdown")
        return

    status_msg = await update.message.reply_text("⏳ *Sedang menyusun & merender dokumen PDF Invoice...*", parse_mode="Markdown")

    # 1. Parse Invoice Data
    inv_create = invoice_parser.parse_invoice_text(raw_args, user_id=user_id)

    # 2. Save Invoice into Storage
    persisted_inv = await get_storage().add_invoice(inv_create)
    user_settings = await get_storage().get_user_settings(user_id)

    # 3. Render PDF Invoice
    pdf_bytes = invoice_generator.generate_pdf(persisted_inv, user_settings)

    await status_msg.delete()

    card_text = (
        f"📄 *INVOICE BERHASIL DIBUAT & DISIMPAN*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧾 *No. Invoice:* `{persisted_inv.id}`\n"
        f"🏢 *Klien:* *{persisted_inv.client_name}*\n"
        f"📁 *Proyek:* _{persisted_inv.project_title}_\n"
        f"💰 *Total Tagihan:* `{format_currency(persisted_inv.amount, persisted_inv.currency)}`\n"
        f"📅 *Jatuh Tempo:* `{persisted_inv.due_date}`\n"
        f"🔖 *Status:* *{persisted_inv.status.value}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"File PDF terlampir di bawah siap dikirimkan ke klien! 👇"
    )

    # Send Card & PDF Document
    await update.message.reply_document(
        document=io.BytesIO(pdf_bytes),
        filename=f"{persisted_inv.id}_{persisted_inv.client_name.replace(' ', '_')}.pdf",
        caption=card_text,
        parse_mode="Markdown",
        reply_markup=get_invoice_action_keyboard(persisted_inv.id),
    )


@restricted
async def cmd_unpaid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all pending unpaid client invoices."""
    user_id = update.effective_user.id
    msg, _ = await piutang_tracker.get_unpaid_invoices_summary(user_id=user_id)
    await update.message.reply_text(msg, parse_mode="Markdown")


@restricted
async def cmd_pay_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mark an invoice as paid and automatically trigger the Income Splitter."""
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await update.message.reply_text("⚠️ Harap sertakan ID Invoice. Contoh: `/pay_invoice INV-202608-A1B2`", parse_mode="Markdown")
        return

    invoice_id = args[0].strip()
    success, msg, _ = await piutang_tracker.settle_invoice_payment(user_id=user_id, invoice_id=invoice_id)
    await update.message.reply_text(msg, parse_mode="Markdown")


@restricted
async def cmd_remind_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate a polite WhatsApp / Email reminder message for a specific invoice."""
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await update.message.reply_text("⚠️ Harap sertakan ID Invoice. Contoh: `/remind_invoice INV-202608-A1B2`", parse_mode="Markdown")
        return

    invoice_id = args[0].strip()
    success, msg = await piutang_tracker.generate_reminder_template(user_id=user_id, invoice_id=invoice_id)
    await update.message.reply_text(msg, parse_mode="Markdown")


@restricted
async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Export all financial summaries, transaction ledger, and invoices to an Excel workbook (.xlsx)."""
    user_id = update.effective_user.id
    status_msg = await update.message.reply_text("📊 *Sedang menyusun file Excel (.xlsx) data keuangan...*", parse_mode="Markdown")

    excel_bytes = await excel_exporter.export_financial_workbook(user_id=user_id)
    await status_msg.delete()

    filename = f"Laporan_Keuangan_Freelance_{get_current_month_year()}.xlsx"
    caption = (
        f"📥 *EXPORT DATA KEUANGAN BERHASIL*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"File Excel ini berisi 3 Sheet lengkap:\n"
        f"1. 📊 *Ringkasan Finansial:* Cashflow, Gaji Pokok, Buffer Fund, Runway\n"
        f"2. 🕒 *Histori Transaksi:* Seluruh data pemasukan & pengeluaran\n"
        f"3. 🧾 *Daftar Invoice:* Daftar piutang & status pembayaran klien"
    )

    await update.message.reply_document(
        document=io.BytesIO(excel_bytes),
        filename=filename,
        caption=caption,
        parse_mode="Markdown",
    )


@restricted
async def cmd_export_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Export complete executive PDF financial report or cheatsheet guide."""
    user_id = update.effective_user.id
    text = (update.message.text or "").lower()
    
    # If user wants guide/cheatsheet PDF
    if "panduan" in text or "kunci" in text or "cheat" in text:
        from tools.generate_cheatsheet_pdf import generate_cheatsheet_pdf
        status_msg = await update.message.reply_text("📄 *Sedang menyusun PDF Panduan & Kunci Bot...*", parse_mode="Markdown")
        pdf_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Panduan_Kunci_Freelance_Finance.pdf")
        generate_cheatsheet_pdf(pdf_path)
        await status_msg.delete()
        
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
            
        await update.message.reply_document(
            document=io.BytesIO(pdf_bytes),
            filename="Panduan_Kunci_Freelance_Finance.pdf",
            caption="📘 *PANDUAN & KUNCI CEPAT BOT FREELANCE FINANCE (PDF)*\n\nSimpan dokumen ini sebagai referensi praktis seluruh perintah dan alur otomatis bot Anda!",
            parse_mode="Markdown",
        )
        return

    # Financial Statement PDF Export
    status_msg = await update.message.reply_text("📄 *Sedang membuat dokumen PDF Laporan Keuangan...*", parse_mode="Markdown")
    storage = get_storage()
    m_y = get_current_month_year()
    summary = await storage.get_monthly_summary(m_y, user_id)
    user_settings = await storage.get_user_settings(user_id)
    transactions = await storage.get_transactions(user_id=user_id, month_year=m_y, limit=100)
    goals = await storage.get_goals(user_id=user_id, is_completed=False)
    subs = await storage.get_subscriptions(user_id=user_id, is_active=True)

    pdf_bytes = pdf_financial_exporter.generate_statement_pdf(
        user_id=user_id,
        month_year=m_y,
        summary=summary,
        settings=user_settings,
        transactions=transactions,
        goals=goals,
        subscriptions=subs,
    )
    await status_msg.delete()

    filename = f"Laporan_Keuangan_{m_y}.pdf"
    caption = (
        f"📑 *LAPORAN KEUANGAN FREELANCE (PDF)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Dokumen PDF resmi bulan *{m_y}* telah selesai dibuat!\n"
        f"• 📊 Ringkasan Eksekutif & Runway\n"
        f"• 🎯 Progres Target & Wishlist\n"
        f"• 💳 Beban Langganan Rutin\n"
        f"• 🕒 Ledger Riwayat Transaksi\n\n"
        f"💡 _Ketik `/pdf panduan` untuk download PDF lembar kunci perintah._"
    )

    await update.message.reply_document(
        document=io.BytesIO(pdf_bytes),
        filename=filename,
        caption=caption,
        parse_mode="Markdown",
    )


@restricted
async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display recent 10 transactions."""
    user_id = update.effective_user.id
    transactions = await get_storage().get_transactions(user_id=user_id, limit=10)

    if not transactions:
        await update.message.reply_text("Belum ada riwayat transaksi yang tercatat.")
        return

    user_settings = await get_storage().get_user_settings(user_id)
    currency = user_settings.currency

    history_lines = ["🕒 *10 TRANSAKSI TERAKHIR:*\n━━━━━━━━━━━━━━━━━━━━━"]
    for i, tx in enumerate(transactions, start=1):
        type_icon = "🟢 +" if tx.type == TransactionType.INCOME else "🔴 -"
        dt_str = tx.timestamp.strftime("%d/%m %H:%M")
        history_lines.append(
            f"{i}. {type_icon} `{format_currency(tx.amount, currency)}` | *{tx.category.value}*\n"
            f"   🏢 {tx.source_or_merchant} ({dt_str})\n"
            f"   📝 _{tx.notes or '-'}_"
        )
    history_lines.append("━━━━━━━━━━━━━━━━━━━━━")
    await update.message.reply_text("\n".join(history_lines), parse_mode="Markdown")


@restricted
async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View and adjust user financial settings."""
    user_id = update.effective_user.id
    user_settings = await get_storage().get_user_settings(user_id)
    currency = user_settings.currency

    settings_text = (
        f"⚙️ *PENGATURAN KEUANGAN & PROFIL FREELANCE*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Nama Freelancer:* `{user_settings.freelancer_name}`\n"
        f"💳 *Rekening Pembayaran:* `{user_settings.payment_details}`\n"
        f"🎯 *Target Gaji Pokok:* `{format_currency(user_settings.target_salary, currency)}`\n"
        f"🏛️ *Potongan Pajak & Ops:* `{user_settings.tax_percentage}%`\n"
        f"🏠 *Batas Budget Needs:* `{format_currency(user_settings.needs_budget, currency)}`\n"
        f"☕ *Batas Budget Wants:* `{format_currency(user_settings.wants_budget, currency)}`\n"
        f"💻 *Batas Budget Operational:* `{format_currency(user_settings.operational_budget, currency)}`\n"
        f"🛡️ *Target Dana Darurat:* `{format_currency(user_settings.emergency_target, currency)}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✏️ *Perintah Mengubah Pengaturan:*\n"
        f"• `/set_name <nama>` — Nama Anda di invoice\n"
        f"• `/set_bank <info bank>` — Rekening pembayaran invoice\n"
        f"• `/set_salary <nominal>` — Target gaji bulanan\n"
        f"• `/set_tax <persen>` — Persentase pajak & cadangan ops\n"
        f"• `/set_needs <nominal>` — Batas pengeluaran Needs\n"
        f"• `/set_wants <nominal>` — Batas pengeluaran Wants\n"
        f"• `/set_ops <nominal>` — Batas pengeluaran Operational"
    )
    await update.message.reply_text(settings_text, parse_mode="Markdown")


@restricted
async def cmd_set_param(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle settings updates: /set_salary, /set_tax, /set_needs, /set_wants, /set_ops, /set_name, /set_bank."""
    user_id = update.effective_user.id
    cmd = update.message.text.split()[0].lower()
    raw_args = update.message.text.split(maxsplit=1)

    if len(raw_args) < 2:
        await update.message.reply_text(f"⚠️ Harap sertakan nilai. Contoh: `{cmd} nilai_baru`", parse_mode="Markdown")
        return

    arg_val = raw_args[1].strip()
    user_settings = await get_storage().get_user_settings(user_id)

    if "name" in cmd:
        user_settings.freelancer_name = arg_val
        field_name = "Nama Freelancer"
        disp_val = arg_val
    elif "bank" in cmd:
        user_settings.payment_details = arg_val
        field_name = "Info Rekening Pembayaran"
        disp_val = arg_val
    else:
        try:
            val_str = arg_val.replace(".", "").replace(",", "").replace("k", "000").replace("jt", "000000").replace("%", "")
            value = float(val_str)
        except ValueError:
            await update.message.reply_text("⚠️ Format angka tidak valid.", parse_mode="Markdown")
            return

        if "salary" in cmd:
            user_settings.target_salary = value
            field_name = "Target Gaji Pokok"
        elif "tax" in cmd:
            user_settings.tax_percentage = value
            field_name = "Persentase Pajak & Cadangan Ops"
        elif "needs" in cmd:
            user_settings.needs_budget = value
            field_name = "Batas Budget Needs"
        elif "wants" in cmd:
            user_settings.wants_budget = value
            field_name = "Batas Budget Wants"
        elif "ops" in cmd:
            user_settings.operational_budget = value
            field_name = "Batas Budget Operational"
        else:
            await update.message.reply_text("Perintah tidak dikenali.")
            return

        disp_val = format_currency(value, user_settings.currency) if "tax" not in cmd else f"{value}%"

    await get_storage().update_user_settings(user_settings)
    await update.message.reply_text(
        f"✅ *{field_name}* berhasil diperbarui menjadi: `{disp_val}`",
        parse_mode="Markdown",
    )


# --- Goals & Wishlist Handlers ---

@restricted
async def cmd_goals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display active wishlist goals with progress bars and ETA."""
    user_id = update.effective_user.id
    storage = get_storage()
    goals = await storage.get_goals(user_id)
    user_settings = await storage.get_user_settings(user_id)
    currency = user_settings.currency
    m_y = get_current_month_year()
    summary = await storage.get_monthly_summary(m_y, user_id)
    avg_income = max(user_settings.target_salary, summary.total_income)

    if not goals:
        empty_msg = (
            "🎯 *TARGET IMPIAN & WISHLIST BELUM ADA*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Anda dapat membuat target belanja / tabungan impian dengan fitur auto-split otomatis dari setiap fee freelance yang masuk!\n\n"
            "💡 *Cara Membuat Target Baru:*\n"
            "• `/add_goal <nama> <target> <alokasi_%>`\n\n"
            "📌 *Contoh Nyata:*\n"
            "• `/add_goal Macbook M3 20jt 10%`\n"
            "• `/add_goal Liburan Bali 8jt 5%`\n"
            "• `/add_goal Dana Darurat 30jt 15%`"
        )
        await update.message.reply_text(empty_msg, parse_mode="Markdown")
        return

    total_target = sum(g.target_amount for g in goals)
    total_saved = sum(g.current_amount for g in goals)
    total_alloc_pct = sum(g.allocation_percent for g in goals if not g.is_completed)

    lines = []
    for idx, g in enumerate(goals, 1):
        status_icon = "🎉 *SELESAI!*" if g.is_completed else render_progress_bar(g.percentage_achieved)
        eta_str = financial_engine.calculate_goal_eta(g, avg_income)
        lines.append(
            f"*{idx}. {g.name}* (Alokasi: `{g.allocation_percent}%`)\n"
            f"  • Progress: {status_icon}\n"
            f"  • Terkumpul: `{format_currency(g.current_amount, currency)}` / `{format_currency(g.target_amount, currency)}`\n"
            f"  • ⏳ Prediksi Tercapai: _{eta_str}_\n"
            f"  • ID: `{g.id}`"
        )

    goals_text = (
        f"🎯 *TARGET IMPIAN & WISHLIST FREELANCE*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        + "\n\n".join(lines) + "\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Total Tabungan Target:* `{format_currency(total_saved, currency)}` / `{format_currency(total_target, currency)}`\n"
        f"⚡ *Total Alokasi Auto-Split:* `{total_alloc_pct}% per fee masuk`\n\n"
        f"💡 _Ketik `/add_goal` untuk tambah target, atau `/delete_goal <id>` untuk hapus._"
    )
    await update.message.reply_text(
        goals_text,
        parse_mode="Markdown",
        reply_markup=get_goals_keyboard(goals),
    )


@restricted
async def cmd_add_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a new financial goal with auto-split allocation: /add_goal <name> <amount> <percent>."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    parts = text.split(maxsplit=3)

    if len(parts) < 3:
        guide = (
            "💡 *Format Perintah Tambah Target:*\n\n"
            "`/add_goal <Nama Target> <Target Nominal> <Alokasi Persen>`\n\n"
            "📌 *Contoh Penggunaan:*\n"
            "• `/add_goal Macbook M3 20jt 10%`\n"
            "• `/add_goal Liburan Bali 8.000.000 5%`\n"
            "• `/add_goal Kursus AI 3jt 5%`"
        )
        await update.message.reply_text(guide, parse_mode="Markdown")
        return

    # Extract percent from last argument or text
    import re
    pct_match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
    if pct_match:
        alloc_percent = float(pct_match.group(1).replace(",", "."))
        clean_text = re.sub(r"\s*\d+(?:[.,]\d+)?\s*%", "", text)
    else:
        # Check last token
        last_tok = parts[-1].replace("%", "").replace(",", ".")
        try:
            alloc_percent = float(last_tok)
            clean_text = " ".join(parts[:-1])
        except ValueError:
            alloc_percent = 10.0
            clean_text = text

    # Extract target amount from clean_text
    amt_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:jt|juta|mio|million)", clean_text, re.IGNORECASE)
    if amt_match:
        target_amt = float(amt_match.group(1).replace(",", ".")) * 1_000_000.0
        name_part = re.sub(r"/add_goal\s+", "", clean_text, flags=re.IGNORECASE)
        name_part = re.sub(r"(\d+(?:[.,]\d+)?)\s*(?:jt|juta|mio|million)", "", name_part, flags=re.IGNORECASE).strip()
    else:
        num_match = re.search(r"(?:rp\.?)?\s*(\d{1,3}(?:\.\d{3})+|\d+)", clean_text, re.IGNORECASE)
        if num_match:
            raw_val = num_match.group(1).replace(".", "")
            target_amt = float(raw_val)
            name_part = re.sub(r"/add_goal\s+", "", clean_text, flags=re.IGNORECASE)
            name_part = re.sub(r"(?:rp\.?)?\s*(\d{1,3}(?:\.\d{3})+|\d+)", "", name_part, flags=re.IGNORECASE).strip()
        else:
            target_amt = 10_000_000.0
            name_part = clean_text.replace("/add_goal", "").strip()

    name = name_part.strip(", -") or "Target Impian"
    user_settings = await get_storage().get_user_settings(user_id)
    currency = user_settings.currency

    goal_create = FinancialGoalCreate(
        user_id=user_id,
        name=name,
        target_amount=target_amt,
        current_amount=0.0,
        allocation_percent=alloc_percent,
        is_completed=False,
    )
    new_goal = await get_storage().add_goal(goal_create)

    resp = (
        f"🎯 *TARGET IMPIAN BERHASIL DIBUAT!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ *Nama Target:* *{new_goal.name}*\n"
        f"💰 *Target Nominal:* `{format_currency(new_goal.target_amount, currency)}`\n"
        f"⚡ *Auto-Split Alokasi:* `{new_goal.allocation_percent}% dari setiap fee masuk`\n"
        f"📊 *Progress:* {render_progress_bar(0.0)}\n"
        f"🆔 *ID Target:* `{new_goal.id}`\n\n"
        f"✨ Setiap kali Anda mencatat fee freelance masuk, `{new_goal.allocation_percent}%` akan otomatis di-plot ke target ini!"
    )
    await update.message.reply_text(resp, parse_mode="Markdown")


@restricted
async def cmd_delete_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a goal: /delete_goal <id>."""
    user_id = update.effective_user.id
    parts = update.message.text.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text("⚠️ Harap sertakan ID target. Contoh: `/delete_goal a1b2c3d4`", parse_mode="Markdown")
        return

    goal_id = parts[1].strip()
    success = await get_storage().delete_goal(goal_id, user_id)
    if success:
        await update.message.reply_text(f"✅ Target `{goal_id}` berhasil dihapus dari daftar impian.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"⚠️ Target dengan ID `{goal_id}` tidak ditemukan.", parse_mode="Markdown")


# --- Subscriptions Handlers ---

@restricted
async def cmd_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display recurring subscriptions and monthly fixed burn rate."""
    user_id = update.effective_user.id
    storage = get_storage()
    subs = await storage.get_subscriptions(user_id)
    user_settings = await storage.get_user_settings(user_id)
    currency = user_settings.currency

    if not subs:
        empty_msg = (
            "💳 *BELUM ADA LANGGANAN RUTIN TERCATAT*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Catat biaya langganan bulanan/tahunan (ChatGPT, VPS, Figma, WiFi, Kos) agar pengeluaran tetap terpantau dan mendapat pengingat H-3 sebelum jatuh tempo!\n\n"
            "💡 *Cara Tambah Langganan:*\n"
            "• `/add_sub <nama> <nominal> <tgl_jatuh_tempo>`\n\n"
            "📌 *Contoh Penggunaan:*\n"
            "• `/add_sub ChatGPT Plus 300rb 15`\n"
            "• `/add_sub VPS Hosting 150k 1`\n"
            "• `/add_sub WiFi Indihome 350rb 20`"
        )
        await update.message.reply_text(empty_msg, parse_mode="Markdown")
        return

    total_monthly_burn = sum(s.amount for s in subs if s.is_active)
    now_day = datetime.now().day

    lines = []
    for idx, s in enumerate(subs, 1):
        status_icon = "🟢 Aktif" if s.is_active else "⚪ Nonaktif"
        days_until = (s.billing_day - now_day) if s.billing_day >= now_day else (30 - now_day + s.billing_day)
        near_alert = "⚠️ *Segera Tagihan!*" if (0 <= days_until <= 3 and s.is_active) else f"_{days_until} hari lagi_"
        lines.append(
            f"*{idx}. {s.name}* — `{format_currency(s.amount, currency)}/{s.billing_cycle}`\n"
            f"  • Jatuh Tempo: Tanggal *{s.billing_day}* ({near_alert})\n"
            f"  • Kategori: *{s.category.value}* | Status: {status_icon}\n"
            f"  • ID: `{s.id}`"
        )

    subs_text = (
        f"💳 *DAFTAR LANGGANAN & BIAYA RUTIN*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        + "\n\n".join(lines) + "\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔥 *Total Monthly Burn Rate (Biaya Tetap):* `{format_currency(total_monthly_burn, currency)} / bulan`\n\n"
        f"💡 _Ketik `/add_sub` untuk tambah, atau `/delete_sub <id>` untuk hapus._"
    )
    await update.message.reply_text(
        subs_text,
        parse_mode="Markdown",
        reply_markup=get_subscriptions_keyboard(subs),
    )


@restricted
async def cmd_add_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a new recurring subscription: /add_sub <name> <amount> <billing_day>."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    parts = text.split(maxsplit=3)

    if len(parts) < 3:
        guide = (
            "💡 *Format Perintah Tambah Langganan:*\n\n"
            "`/add_sub <Nama Layanan> <Nominal> <Tanggal Tagihan (1-31)>`\n\n"
            "📌 *Contoh Penggunaan:*\n"
            "• `/add_sub ChatGPT Plus 300rb 15`\n"
            "• `/add_sub VPS DigitalOcean 150k 1`\n"
            "• `/add_sub WiFi Kantor 350.000 20`"
        )
        await update.message.reply_text(guide, parse_mode="Markdown")
        return

    import re
    # Extract day (1-31) from end or text
    day_match = re.search(r"\b([1-9]|[12]\d|3[01])\b$", text)
    if day_match:
        billing_day = int(day_match.group(1))
        clean_text = text[:day_match.start()].strip()
    else:
        billing_day = 1
        clean_text = text

    # Extract amount
    amt_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:jt|juta|k|rb|ribu)", clean_text, re.IGNORECASE)
    if amt_match:
        val_str = amt_match.group(1).replace(",", ".")
        multiplier = 1_000_000.0 if any(u in amt_match.group(0).lower() for u in ["jt", "juta"]) else 1_000.0
        amount = float(val_str) * multiplier
        name_part = re.sub(r"/add_sub\s+", "", clean_text, flags=re.IGNORECASE)
        name_part = re.sub(r"(\d+(?:[.,]\d+)?)\s*(?:jt|juta|k|rb|ribu)", "", name_part, flags=re.IGNORECASE).strip()
    else:
        num_match = re.search(r"(?:rp\.?)?\s*(\d{1,3}(?:\.\d{3})+|\d+)", clean_text, re.IGNORECASE)
        if num_match:
            raw_val = num_match.group(1).replace(".", "")
            amount = float(raw_val)
            name_part = re.sub(r"/add_sub\s+", "", clean_text, flags=re.IGNORECASE)
            name_part = re.sub(r"(?:rp\.?)?\s*(\d{1,3}(?:\.\d{3})+|\d+)", "", name_part, flags=re.IGNORECASE).strip()
        else:
            amount = 100_000.0
            name_part = clean_text.replace("/add_sub", "").strip()

    name = name_part.strip(", -") or "Langganan Rutin"
    user_settings = await get_storage().get_user_settings(user_id)
    currency = user_settings.currency

    # Auto category
    name_lower = name.lower()
    if any(kw in name_lower for kw in ["vps", "hosting", "domain", "chatgpt", "figma", "github", "adobe", "canva"]):
        category = Category.OPERATIONAL
    elif any(kw in name_lower for kw in ["netflix", "spotify", "youtube", "game", "steam"]):
        category = Category.WANTS
    else:
        category = Category.NEEDS

    sub_create = SubscriptionCreate(
        user_id=user_id,
        name=name,
        amount=amount,
        billing_cycle="monthly",
        billing_day=billing_day,
        category=category,
        is_active=True,
    )
    new_sub = await get_storage().add_subscription(sub_create)

    resp = (
        f"💳 *LANGGANAN BERHASIL DITAMBAHKAN!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ *Layanan:* *{new_sub.name}*\n"
        f"💸 *Biaya:* `{format_currency(new_sub.amount, currency)} / bulan`\n"
        f"📅 *Jatuh Tempo:* Setiap tanggal *{new_sub.billing_day}*\n"
        f"📂 *Kategori:* *{new_sub.category.value}*\n"
        f"🆔 *ID:* `{new_sub.id}`\n\n"
        f"🔔 Bot akan otomatis mengingatkan Anda H-3 sebelum tanggal perpanjangan!"
    )
    await update.message.reply_text(resp, parse_mode="Markdown")


@restricted
async def cmd_delete_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a subscription: /delete_sub <id>."""
    user_id = update.effective_user.id
    parts = update.message.text.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text("⚠️ Harap sertakan ID langganan. Contoh: `/delete_sub a1b2c3d4`", parse_mode="Markdown")
        return

    sub_id = parts[1].strip()
    success = await get_storage().delete_subscription(sub_id, user_id)
    if success:
        await update.message.reply_text(f"✅ Langganan `{sub_id}` berhasil dihapus.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"⚠️ Langganan dengan ID `{sub_id}` tidak ditemukan.", parse_mode="Markdown")


# --- AI Advisor & Health Score Handlers ---

@restricted
async def cmd_advisor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Consult Gemini AI Financial Advisor on purchases, savings, and runway decisions."""
    user_id = update.effective_user.id
    raw_args = update.message.text.split(maxsplit=1)

    if len(raw_args) < 2:
        guide = (
            "🤖 *AI FINANCIAL COACH & ADVISOR*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Konsultasikan keputusan finansial Anda secara langsung dengan AI Gemini!\n\n"
            "💡 *Contoh Pertanyaan yang Bisa Diajukan:*\n"
            "• `/advisor apakah aman kalau saya beli iPad 8jt bulan ini?`\n"
            "• `/advisor bagaimana cara memperkuat buffer runway saya?`\n"
            "• `/advisor evaluasi pengeluaran dan kuota wants saya saat ini`\n"
            "• `/advisor strategi alokasi tabungan untuk freelancer pemula`\n\n"
            "📌 _Atau cukup ketik pertanyaan langsung diawali kata 'tanya:' atau 'apakah aman'_"
        )
        await update.message.reply_text(guide, parse_mode="Markdown")
        return

    question = raw_args[1].strip()
    status_msg = await update.message.reply_text("🧠 *AI Financial Coach sedang menganalisis kondisi keuangan Anda...*", parse_mode="Markdown")

    try:
        storage = get_storage()
        m_y = get_current_month_year()
        summary = await storage.get_monthly_summary(m_y, user_id)
        user_settings = await storage.get_user_settings(user_id)
        currency = user_settings.currency
        transactions = await storage.get_transactions(user_id=user_id, month_year=m_y, limit=500)
        goals = await storage.get_goals(user_id=user_id, is_completed=False)
        subs = await storage.get_subscriptions(user_id=user_id, is_active=True)

        needs_spent = sum(tx.amount for tx in transactions if tx.type == TransactionType.EXPENSE and tx.category == Category.NEEDS)
        wants_spent = sum(tx.amount for tx in transactions if tx.type == TransactionType.EXPENSE and tx.category == Category.WANTS)

        goals_summary = ", ".join([f"{g.name} (Terkumpul {format_currency(g.current_amount, currency)}/{format_currency(g.target_amount, currency)}, {g.percentage_achieved}%)" for g in goals]) or "Tidak ada target aktif"
        subs_summary = ", ".join([f"{s.name} ({format_currency(s.amount, currency)}/bln tgl {s.billing_day})" for s in subs]) or "Tidak ada langganan tetap"

        context_data = {
            "month_year": m_y,
            "currency": currency,
            "total_income": format_currency(summary.total_income, currency),
            "total_expense": format_currency(summary.total_expense, currency),
            "buffer_runway_months": summary.buffer_runway_months,
            "buffer_fund_balance": format_currency(summary.buffer_fund_balance, currency),
            "needs_spent": format_currency(needs_spent, currency),
            "needs_budget": format_currency(user_settings.needs_budget, currency),
            "wants_spent": format_currency(wants_spent, currency),
            "wants_budget": format_currency(user_settings.wants_budget, currency),
            "target_salary": format_currency(user_settings.target_salary, currency),
            "actual_salary_drawn": format_currency(summary.actual_salary_drawn, currency),
            "active_goals_summary": goals_summary,
            "subscriptions_summary": subs_summary,
        }

        advice = await gemini_engine.ask_financial_advisor(context_data, question)
        await status_msg.delete()
        await update.message.reply_text(f"🤖 *SARAN FINANSIAL AI:*\n\n{advice}", parse_mode="Markdown")

    except Exception as e:
        logger.error("Error running AI Advisor: %s", e, exc_info=True)
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text("⚠️ Terjadi kendala saat berkonsultasi dengan AI Advisor.")


@restricted
async def cmd_health_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Calculate and display comprehensive freelance financial health score."""
    user_id = update.effective_user.id
    report = await financial_engine.calculate_financial_health_score(user_id)
    await update.message.reply_text(report.summary_text, parse_mode="Markdown")


@restricted
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Download receipt image, run OpenAI Vision OCR, and display confirmation card."""
    user_id = update.effective_user.id
    photo = update.message.photo[-1]

    status_msg = await update.message.reply_text("🔍 *AI Vision OCR:* Sedang menganalisis struk / invoice...", parse_mode="Markdown")

    file = await context.bot.get_file(photo.file_id)
    photo_bytes = bytes(await file.download_as_bytearray())

    parsed = await ocr_engine.extract_receipt(photo_bytes)
    await status_msg.delete()

    user_settings = await get_storage().get_user_settings(user_id)
    currency = user_settings.currency

    pending_id = str(uuid.uuid4())[:8]
    context.user_data[f"pending_tx_{pending_id}"] = {
        "user_id": user_id,
        "type": parsed.type.value,
        "category": parsed.category.value,
        "amount": parsed.amount,
        "source_or_merchant": parsed.source_or_merchant,
        "notes": parsed.notes,
        "timestamp": datetime.now().isoformat(),
    }

    items_list_str = "\n".join([f"  • {item}" for item in (parsed.items or [])[:5]])
    items_display = f"\n📦 *Item Terdeteksi:*\n{items_list_str}" if items_list_str else ""

    preview_card = (
        f"🧾 *PREVIEW STRUK AI OCR*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏪 *Merchant / Toko:* `{parsed.source_or_merchant}`\n"
        f"💰 *Total Nominal:* `{format_currency(parsed.amount, currency)}`\n"
        f"📂 *Kategori Terpilih:* *{parsed.category.value}*\n"
        f"🔖 *Tipe:* *{parsed.type.value}*\n"
        f"📅 *Tanggal:* `{parsed.date or datetime.now().strftime('%Y-%m-%d')}`"
        f"{items_display}\n"
        f"📝 *Catatan:* _{parsed.notes or '-'}_{f' (Akurasi: {int(parsed.confidence*100)}%)'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Apakah data di atas sudah benar?"
    )

    await update.message.reply_text(
        preview_card,
        parse_mode="Markdown",
        reply_markup=get_confirmation_keyboard(pending_id),
    )


# --- Quotations & SPH Commands ---

@restricted
async def cmd_quote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create and export a formal Quotation / Surat Penawaran Harga (SPH) PDF."""
    user_id = update.effective_user.id
    raw_text = update.message.text or ""
    
    parsed = quotation_parser.parse_command_text(raw_text, user_id)
    if not parsed:
        help_text = (
            "📄 *CARA MEMBUAT SURAT PENAWARAN HARGA (QUOTATION/SPH)*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Gunakan format praktis berikut:\n"
            "`/quote <Klien> | <Proyek> | <Nominal> | <Durasi> | <Syarat DP>`\n\n"
            "📌 *Contoh Penggunaan Nyata:*\n"
            "• `/quote PT Maju Jaya | Redesign Website E-Commerce | 15jt | 14 Hari Kerja | DP 50%`\n"
            "• `/quote Studio Animasi | 3D Modeling Asset | 8.500.000 | 7 Hari Kerja`\n\n"
            "💡 _Bot akan otomatis membuat dokumen PDF Surat Penawaran Harga resmi dengan klausul batas revisi dan DP siap kirim ke klien!_"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")
        return

    status_msg = await update.message.reply_text("⏳ *Sedang menyusun dokumen PDF Surat Penawaran Harga (SPH)...*", parse_mode="Markdown")
    storage = get_storage()
    created_quote = await storage.add_quotation(parsed)
    user_settings = await storage.get_user_settings(user_id)

    pdf_bytes = quotation_generator.generate_pdf(created_quote, user_settings)
    await status_msg.delete()

    filename = f"SPH_{created_quote.id}_{created_quote.client_name.replace(' ', '_')}.pdf"
    caption = (
        f"📄 *SURAT PENAWARAN HARGA (SPH) RESMI*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"No. Dokumen: `{created_quote.id}`\n"
        f"🏢 Klien: *{created_quote.client_name}*\n"
        f"🎯 Proyek: *{created_quote.project_title}*\n"
        f"💰 Total Estimasi: *{format_currency(created_quote.amount, created_quote.currency)}*\n"
        f"⏳ Durasi: `{created_quote.timeline}`\n"
        f"📅 Berlaku Hingga: `{created_quote.valid_until}`\n"
        f"📝 Ketentuan: _{created_quote.dp_terms}_\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Dokumen PDF proposal penawaran harga terlampir siap dikirimkan ke klien Anda."
    )

    await update.message.reply_document(
        document=io.BytesIO(pdf_bytes),
        filename=filename,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=get_quotation_action_keyboard(created_quote.id),
    )


@restricted
async def cmd_quotes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all active quotation proposals."""
    user_id = update.effective_user.id
    storage = get_storage()
    quotes = await storage.get_quotations(user_id=user_id, limit=20)

    if not quotes:
        await update.message.reply_text(
            "Belum ada Surat Penawaran Harga (SPH) yang dibuat.\nKetik `/quote` untuk membuat penawaran baru!",
            parse_mode="Markdown",
        )
        return

    user_settings = await storage.get_user_settings(user_id)
    currency = user_settings.currency

    lines = ["📄 *DAFTAR SURAT PENAWARAN HARGA (SPH)*\n━━━━━━━━━━━━━━━━━━━━━"]
    for i, q in enumerate(quotes, start=1):
        status_icon = "🟢" if q.status == QuotationStatus.ACCEPTED else ("📑" if q.status == QuotationStatus.SENT else "⚪")
        lines.append(
            f"{i}. {status_icon} *{q.client_name}* — `{format_currency(q.amount, currency)}`\n"
            f"   🎯 _{q.project_title}_\n"
            f"   ⏳ Durasi: `{q.timeline}` | Expired: `{q.valid_until}`\n"
            f"   ID: `{q.id}` (Status: *{q.status.value}*)"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 _Gunakan tombol di bawah untuk unduh PDF atau konversi ke invoice._")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_quotations_keyboard(quotes),
    )


# --- Project Termins & Milestones Commands ---

@restricted
async def cmd_termin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create or view project termin milestones."""
    user_id = update.effective_user.id
    raw_text = update.message.text or ""

    parsed = termin_tracker.parse_termin_command(raw_text, user_id)
    if not parsed:
        help_text = (
            "⏳ *CARA MEMBUAT PROYEK TERMIN & MILESTONES*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Gunakan format berikut:\n"
            "`/termin <Klien> | <Nama Proyek> | <Total Nilai> | <Persentase Termin>`\n\n"
            "📌 *Contoh Penggunaan Nyata:*\n"
            "• `/termin PT Maju Jaya | Redesign Website | 15jt | 50% 30% 20%`\n"
            "• `/termin Studio ABC | Mobile App Flutter | 20.000.000 | 50 50`\n"
            "• `/termin Klien XYZ | Jasa Konsultasi | 6jt` _(Default DP 50%, Final 50%)_\n\n"
            "💡 _Bot akan melacak tiap tahapan termin dan menerbitkan invoice resmi per termin secara otomatis!_"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")
        return

    storage = get_storage()
    created_termin = await storage.add_termin(parsed)
    card_text = termin_tracker.render_termin_card(created_termin)

    await update.message.reply_text(
        card_text,
        parse_mode="Markdown",
        reply_markup=get_termin_action_keyboard(created_termin.id),
    )


@restricted
async def cmd_termins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all active project termins."""
    user_id = update.effective_user.id
    storage = get_storage()
    termins = await storage.get_termins(user_id=user_id, is_completed=False, limit=10)

    if not termins:
        await update.message.reply_text(
            "Tidak ada proyek termin aktif saat ini.\nKetik `/termin` untuk mendaftarkan proyek baru!",
            parse_mode="Markdown",
        )
        return

    user_settings = await storage.get_user_settings(user_id)
    currency = user_settings.currency

    lines = ["⏳ *DAFTAR PROYEK TERMIN AKTIF*\n━━━━━━━━━━━━━━━━━━━━━"]
    for i, t in enumerate(termins, start=1):
        lines.append(
            f"{i}. 🏢 *{t.client_name}* — `{format_currency(t.total_amount, currency)}`\n"
            f"   🎯 _{t.project_title}_\n"
            f"   💵 Sudah Ditagih: `{format_currency(t.total_billed, currency)}` | Sisa: `*{format_currency(t.total_unbilled, currency)}*`\n"
            f"   ID: `{t.id}`"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_termins_keyboard(termins),
    )


# --- Instant Affordability Radar Command ---

@restricted
async def cmd_affordability_radar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Instant Affordability Radar ('Boleh Beli Nggak?')."""
    user_id = update.effective_user.id
    raw_text = update.message.text or ""
    clean = raw_text.strip()
    for cmd in ["/beli", "/can_i_buy", "/afford"]:
        if clean.lower().startswith(cmd):
            clean = clean[len(cmd):].strip()
            break

    if not clean:
        help_text = (
            "🎯 *RADAR KELAYAKAN BELANJA ('Boleh Beli Nggak?')*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Ingin beli barang mahal tapi ragu apakah keuanganmu aman?\n\n"
            "Ketik perintah:\n"
            "`/beli <Nama Barang> <Harga>`\n\n"
            "📌 *Contoh Penggunaan:*\n"
            "• `/beli PS5 Slim 7.5jt`\n"
            "• `/beli Sepatu Running 1.8jt`\n"
            "• `/beli Monitor 4K 4.500.000`\n\n"
            "💡 _AI akan menganalisis kuota Wants, dampak terhadap Runway dana darurat, dan target tabunganmu secara instan!_"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")
        return

    # Parse Item Name & Price
    parts = clean.split()
    if len(parts) >= 2:
        price = NLPParser._parse_indonesian_number(parts[-1])
        item_name = " ".join(parts[:-1])
    else:
        price = NLPParser._parse_indonesian_number(clean)
        item_name = "Barang Impian"

    if price <= 0:
        await update.message.reply_text("Mohon sertakan nominal harga yang valid. Contoh: `/beli PS5 7.5jt`", parse_mode="Markdown")
        return

    storage = get_storage()
    m_y = get_current_month_year()
    summary = await storage.get_monthly_summary(m_y, user_id)
    user_settings = await storage.get_user_settings(user_id)
    goals = await storage.get_goals(user_id=user_id, is_completed=False)
    subs = await storage.get_subscriptions(user_id=user_id, is_active=True)

    # Get wants spent this month
    txs = await storage.get_transactions(user_id=user_id, month_year=m_y, limit=200)
    wants_spent = sum(t.amount for t in txs if t.category == Category.WANTS and t.type == TransactionType.EXPENSE)

    report = affordability_radar.evaluate_purchase(
        item_name=item_name,
        price=price,
        summary=summary,
        settings=user_settings,
        wants_spent=wants_spent,
        active_goals=goals,
        active_subs=subs,
    )

    await update.message.reply_text(report.summary_card, parse_mode="Markdown")


# --- 90-Day Cashflow Forecast Command ---

@restricted
async def cmd_forecast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """90-Day forward cashflow simulation."""
    user_id = update.effective_user.id
    status_msg = await update.message.reply_text("🔮 *Sedang menjalankan simulasi arus kas 90 hari kedepan...*", parse_mode="Markdown")

    storage = get_storage()
    m_y = get_current_month_year()
    summary = await storage.get_monthly_summary(m_y, user_id)
    user_settings = await storage.get_user_settings(user_id)
    unpaid_invoices = await storage.get_invoices(user_id=user_id, status=InvoiceStatus.UNPAID)
    subs = await storage.get_subscriptions(user_id=user_id, is_active=True)
    termins = await storage.get_termins(user_id=user_id, is_completed=False)

    report = cashflow_forecaster.forecast_90_days(
        summary=summary,
        settings=user_settings,
        unpaid_invoices=unpaid_invoices,
        active_subscriptions=subs,
        active_termins=termins,
    )
    await status_msg.delete()

    await update.message.reply_text(report.summary_card, parse_mode="Markdown")


# --- Multi-Currency & Realtime Forex Commands ---

@restricted
async def cmd_kurs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display realtime forex exchange rates table against IDR."""
    rates_card = await currency_converter.render_rates_table()
    await update.message.reply_text(
        rates_card,
        parse_mode="Markdown",
        reply_markup=get_currency_keyboard(),
    )


@restricted
async def cmd_convert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert foreign currency to IDR with optional platform fee calculation."""
    raw_text = update.message.text or ""
    clean = raw_text.strip()
    for cmd in ["/convert", "/kurs", "/fx"]:
        if clean.lower().startswith(cmd):
            clean = clean[len(cmd):].strip()
            break

    if not clean:
        await cmd_kurs(update, context)
        return

    import re
    # Extract amount
    amt_match = re.search(r"(\d+(?:[.,]\d+)?)", clean)
    if not amt_match:
        await update.message.reply_text("Format konversi salah. Contoh: `/convert 500 USD` atau `/convert 450 USD upwork`", parse_mode="Markdown")
        return

    amount = float(amt_match.group(1).replace(",", "."))

    # Extract currency code or symbol
    from_curr = "USD"
    if "$" in clean:
        from_curr = "USD"
    elif "€" in clean:
        from_curr = "EUR"
    elif "£" in clean:
        from_curr = "GBP"
    else:
        for c in ["USD", "EUR", "SGD", "GBP", "JPY", "AUD", "MYR", "CNY", "USDT"]:
            if c.lower() in clean.lower():
                from_curr = c
                break

    # Extract platform if specified
    platform = "direct"
    for p in ["upwork", "fiverr", "paypal", "wise"]:
        if p in clean.lower():
            platform = p
            break

    result = await currency_converter.convert_to_idr(amount, from_curr, platform)
    await update.message.reply_text(result.summary_text, parse_mode="Markdown")


# --- AI Tax Estimator & SPT Tahunan Form 1770 Commands ---

@restricted
async def cmd_pajak(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Calculate annual freelance tax projection, PTKP, and PPh Pasal 17 brackets."""
    user_id = update.effective_user.id
    target_msg = update.message or (update.callback_query.message if update.callback_query else None)
    if not target_msg:
        return

    status_msg = await target_msg.reply_text("🧾 *Sedang menghitung simulasi pajak freelance & SPT Form 1770...*", parse_mode="Markdown")

    storage = get_storage()
    user_settings = await storage.get_user_settings(user_id)
    year = datetime.now().year

    # Get all summaries for the current tax year
    all_summaries = []
    for m in range(1, 13):
        m_str = f"{year}-{m:02d}"
        s = await storage.get_monthly_summary(m_str, user_id)
        if s:
            all_summaries.append(s)

    report = tax_estimator.calculate_annual_tax_report(
        year=year,
        all_monthly_summaries=all_summaries,
        settings=user_settings,
        method=TaxMethod.NPPN_FREELANCE,
    )
    if status_msg:
        try:
            await status_msg.delete()
        except Exception:
            pass

    try:
        await target_msg.reply_text(
            report.summary_card,
            parse_mode="Markdown",
            reply_markup=get_tax_keyboard(),
        )
    except Exception as e:
        logger.warning("Markdown parse failed in cmd_pajak, falling back to plain text: %s", e)
        await target_msg.reply_text(
            report.summary_card,
            reply_markup=get_tax_keyboard(),
        )


@restricted
async def cmd_export_spt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Export official DJP Form 1770 Rekapitulasi Peredaran Bruto PDF."""
    user_id = update.effective_user.id
    target_msg = update.message or (update.callback_query.message if update.callback_query else None)
    if not target_msg:
        return

    status_msg = await target_msg.reply_text("📄 *Menyusun dokumen PDF SPT Tahunan Form 1770...*", parse_mode="Markdown")

    storage = get_storage()
    user_settings = await storage.get_user_settings(user_id)
    year = datetime.now().year

    all_summaries = []
    for m in range(1, 13):
        m_str = f"{year}-{m:02d}"
        s = await storage.get_monthly_summary(m_str, user_id)
        if s:
            all_summaries.append(s)

    report = tax_estimator.calculate_annual_tax_report(
        year=year,
        all_monthly_summaries=all_summaries,
        settings=user_settings,
        method=TaxMethod.NPPN_FREELANCE,
    )

    pdf_bytes = pdf_financial_exporter.generate_spt_tax_report_pdf(report, user_settings)
    if status_msg:
        try:
            await status_msg.delete()
        except Exception:
            pass

    filename = f"SPT_1770_Rekap_Peredaran_Bruto_{year}.pdf"
    caption = (
        f"📑 *DOKUMEN REKAPITULASI SPT TAHUNAN FORM 1770 (TAHUN PAJAK {year})*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Wajib Pajak: *{user_settings.freelancer_name}*\n"
        f"💰 Total Omzet: *{format_currency(report.total_annual_gross, 'IDR')}*\n"
        f"⚖️ PPh Terutang: *{format_currency(report.total_tax_due, 'IDR')}*\n\n"
        f"Dokumen resmi ini siap disalin ke e-Form SPT 1770 di DJP Online (djponline.pajak.go.id)."
    )

    try:
        await target_msg.reply_document(
            document=io.BytesIO(pdf_bytes),
            filename=filename,
            caption=caption,
            parse_mode="Markdown",
        )
    except Exception:
        await target_msg.reply_document(
            document=io.BytesIO(pdf_bytes),
            filename=filename,
            caption=caption,
        )


# --- Hourly Rate & Project Pricing Commands ---

@restricted
async def cmd_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Calculate freelance Minimum Acceptable Rate (MAR) and 3-tier project estimation."""
    user_id = update.effective_user.id
    raw_text = update.message.text or ""
    clean = raw_text.strip()
    for cmd in ["/rate", "/hitung_harga", "/pricing", "/harga"]:
        if clean.lower().startswith(cmd):
            clean = clean[len(cmd):].strip()
            break

    storage = get_storage()
    user_settings = await storage.get_user_settings(user_id)

    if not clean:
        mar = pricing_calculator.calculate_minimum_hourly_rate(user_settings)
        currency = user_settings.currency or "IDR"
        help_text = (
            f"⏱️ *TARIF PER JAM & KALKULATOR HARGA PROYEK*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ *Tarif Minimum Kamu (MAR):* `*{format_currency(mar, currency)} / Jam*`\n\n"
            f"💡 *Cara Menghitung Estimasi Harga Proyek:*\n"
            f"`/rate <Nama Proyek> <Estimasi Jam> [Kompleksitas]`\n\n"
            f"📌 *Contoh Penggunaan:*\n"
            f"• `/rate Redesign Web E-Commerce 30 jam`\n"
            f"• `/rate Mobile App Flutter 50 jam Complex`\n"
            f"• `/rate 20 jam`\n\n"
            f"_AI akan meracikkan 3 pilihan harga: Batas Bawah Modal, Standar Pasar, dan Harga Premium Value-Based!_"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")
        return

    import re
    hours_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:jam|hours?|h)?", clean, re.IGNORECASE)
    estimated_hours = float(hours_match.group(1).replace(",", ".")) if hours_match else 20.0

    complexity = "Medium"
    if "complex" in clean.lower() or "rumit" in clean.lower() or "sulit" in clean.lower():
        complexity = "Complex"
    elif "simple" in clean.lower() or "mudah" in clean.lower() or "ringan" in clean.lower():
        complexity = "Simple"

    clean_title = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:jam|hours?|h)?\b", "", clean, flags=re.IGNORECASE)
    clean_title = re.sub(r"\b(complex|rumit|sulit|simple|mudah|medium)\b", "", clean_title, flags=re.IGNORECASE).strip()
    project_title = clean_title or "Proyek Freelance"

    report = pricing_calculator.calculate_project_pricing(
        project_title=project_title,
        estimated_hours=estimated_hours,
        settings=user_settings,
        complexity_level=complexity,
    )

    await update.message.reply_text(report.summary_card, parse_mode="Markdown")


@restricted
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parse conversational natural language inputs or quick keyboard button clicks."""
    text = update.message.text.strip()
    user_id = update.effective_user.id

    # Check for Menu Button Shortcuts
    if text in ["📊 Status Budget", "📊 Status"]:
        await cmd_status(update, context)
        return
    elif text in ["📈 Laporan Bulan Ini", "📈 Laporan"]:
        await cmd_report(update, context)
        return
    elif text in ["🎯 Target & Goals", "🎯 Goals", "🎯 Wishlist"]:
        await cmd_goals(update, context)
        return
    elif text in ["💳 Tagihan Rutin", "💳 Langganan Rutin", "💳 Subscriptions"]:
        await cmd_subscriptions(update, context)
        return
    elif text in ["🌐 Kurs Valas", "🌐 Kurs", "🌐 Valas"]:
        await cmd_kurs(update, context)
        return
    elif text in ["🧾 Pajak SPT 1770", "🧾 Pajak", "🧾 SPT"]:
        await cmd_pajak(update, context)
        return
    elif text in ["⏱️ Hitung Tarif", "⏱️ Tarif", "⏱️ Rate"]:
        await cmd_rate(update, context)
        return
    elif text in ["🤖 Tanya AI Advisor", "🤖 AI Advisor"]:
        await cmd_advisor(update, context)
        return
    elif text in ["🏆 Skor Keuangan", "📊 Skor Keuangan"]:
        await cmd_health_score(update, context)
        return
    elif text in ["📄 Surat Penawaran", "📄 SPH", "📄 Quotation"]:
        await cmd_quotes(update, context)
        return
    elif text in ["⏳ Proyek Termin", "⏳ Termin"]:
        await cmd_termins(update, context)
        return
    elif text in ["🔮 Forecast 90 Hari", "🔮 Forecast"]:
        await cmd_forecast(update, context)
        return
    elif text == "🧾 Buat Invoice":
        await cmd_invoice(update, context)
        return
    elif text == "⏰ Piutang Klien":
        await cmd_unpaid(update, context)
        return
    elif text == "🛡️ Buffer Runway":
        await cmd_buffer(update, context)
        return
    elif text == "📥 Export Excel":
        await cmd_export(update, context)
        return
    elif text == "🕒 Riwayat Transaksi":
        await cmd_history(update, context)
        return
    elif text == "⚙️ Pengaturan":
        await cmd_settings(update, context)
        return
    elif text == "❓ Bantuan":
        await cmd_help(update, context)
        return

    # Check for conversational Affordability Radar triggers
    text_lower = text.lower()
    if text_lower.startswith("beli:") or text_lower.startswith("boleh beli") or text_lower.startswith("bisa beli"):
        import re
        clean_item = re.sub(r"^(?:beli\s*:|boleh beli|bisa beli)\s*", "", text, flags=re.IGNORECASE)
        update.message.text = f"/beli {clean_item}"
        await cmd_affordability_radar(update, context)
        return
    if (
        text_lower.startswith("tanya:")
        or text_lower.startswith("advisor:")
        or text_lower.startswith("apakah aman")
        or text_lower.startswith("boleh beli")
        or text_lower.startswith("bisa beli")
        or "evaluasi keuangan" in text_lower
        or "saran keuangan" in text_lower
    ):
        import re
        clean_q = re.sub(r"^(?:tanya|advisor)\s*:\s*", "", text, flags=re.IGNORECASE)
        update.message.text = f"/advisor {clean_q}"
        await cmd_advisor(update, context)
        return

    # Check for "Invoice [X] lunas" conversational settlement trigger
    if "invoice" in text.lower() and "lunas" in text.lower():
        import re
        # Try extracting invoice ID
        inv_match = re.search(r"INV-\d{6}-[A-Za-z0-9]+", text, re.IGNORECASE)
        if inv_match:
            inv_id = inv_match.group(0).upper()
            success, msg, _ = await piutang_tracker.settle_invoice_payment(user_id=user_id, invoice_id=inv_id)
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

    # Parse Multi-Item NLP Intent & Transaction Details
    parsed_items = await nlp_parser.parse_multi_text(text)
    if not parsed_items:
        parsed_items = [await nlp_parser.parse_text(text)]

    user_settings = await get_storage().get_user_settings(user_id)
    currency = user_settings.currency

    if len(parsed_items) == 1:
        parsed = parsed_items[0]
        if parsed.type == TransactionType.INCOME:
            tx_create = TransactionCreate(
                user_id=user_id,
                timestamp=datetime.now(),
                type=TransactionType.INCOME,
                category=parsed.category,
                amount=parsed.amount,
                source_or_merchant=parsed.source_or_merchant,
                notes=parsed.notes,
            )
            persisted_tx, split_result = await financial_engine.process_income(tx_create)
            await update.message.reply_text(
                split_result.message,
                parse_mode="Markdown",
                reply_markup=get_undo_keyboard(persisted_tx.id),
            )

        else:
            tx_create = TransactionCreate(
                user_id=user_id,
                timestamp=datetime.now(),
                type=TransactionType.EXPENSE,
                category=parsed.category,
                amount=parsed.amount,
                source_or_merchant=parsed.source_or_merchant,
                notes=parsed.notes,
            )
            persisted_tx, guard_result = await financial_engine.process_expense(tx_create)

            status_icon = "🚨" if guard_result.status == BudgetGuardStatus.BREACH else ("⚠️" if guard_result.status == BudgetGuardStatus.WARNING else "✅")
            note_text = tx_create.notes or '-'
            safe_info = await financial_engine.get_daily_safe_spend(user_id)

            expense_resp = (
                f"{status_icon} *PENGELUARAN TERCATAT*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"💸 *Nominal:* `{format_currency(tx_create.amount, currency)}`\n"
                f"📂 *Kategori:* *{tx_create.category.value}*\n"
                f"🏢 *Toko / Keperluan:* `{tx_create.source_or_merchant}`\n"
                f"📝 *Catatan:* _{note_text}_\n\n"
                f"📊 *Status Anggaran ({tx_create.category.value}):*\n"
                f"• {render_progress_bar(guard_result.percentage_used)}\n"
                f"• Terpakai: `{format_currency(guard_result.total_spent, currency)}` / `{format_currency(guard_result.budget_limit, currency)}`\n"
                f"• Sisa Kuota: `{format_currency(guard_result.remaining_budget, currency)}`\n\n"
                f"🎯 *Batas Aman Harian:* `{format_currency(safe_info['daily_safe_limit'], currency)}/hari` (Sisa {safe_info['days_remaining']} hari)\n\n"
                f"{guard_result.message}"
            )
            await update.message.reply_text(
                expense_resp,
                parse_mode="Markdown",
                reply_markup=get_undo_keyboard(persisted_tx.id),
            )

    else:
        # BATCH MULTI-ITEM PROCESSING
        total_batch = 0.0
        item_lines = []
        last_tx_id = ""

        for idx, item in enumerate(parsed_items, 1):
            tx_create = TransactionCreate(
                user_id=user_id,
                timestamp=datetime.now(),
                type=item.type,
                category=item.category,
                amount=item.amount,
                source_or_merchant=item.source_or_merchant,
                notes=item.notes,
            )
            if item.type == TransactionType.INCOME:
                persisted_tx, _ = await financial_engine.process_income(tx_create)
                icon = "💰"
            else:
                persisted_tx, _ = await financial_engine.process_expense(tx_create)
                icon = "💸"

            last_tx_id = persisted_tx.id
            total_batch += item.amount
            cat_icon = "🏠" if item.category == Category.NEEDS else ("☕" if item.category == Category.WANTS else "💻")
            item_lines.append(f"{idx}. {cat_icon} *{item.source_or_merchant}:* `{format_currency(item.amount, currency)}` — _{item.notes}_")

        safe_info = await financial_engine.get_daily_safe_spend(user_id)
        batch_resp = (
            f"⚡ *BATCH TRANSAKSI TERCATAT ({len(parsed_items)} Item)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(item_lines) + "\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 *Total Transaksi Batch:* `{format_currency(total_batch, currency)}`\n\n"
            f"🎯 *Batas Aman Belanja:* `{format_currency(safe_info['daily_safe_limit'], currency)}/hari` (Sisa {safe_info['days_remaining']} hari)"
        )
        await update.message.reply_text(
            batch_resp,
            parse_mode="Markdown",
            reply_markup=get_undo_keyboard(last_tx_id),
        )


@restricted
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process incoming Telegram Voice Note, transcribe with Gemini Free Tier, and log transactions."""
    user_id = update.effective_user.id
    voice = update.message.voice
    if not voice:
        return

    status_msg = await update.message.reply_text("🎙️ *Mendengarkan Voice Note...*", parse_mode="Markdown")

    try:
        file = await context.bot.get_file(voice.file_id)
        voice_bytes = await file.download_as_bytearray()

        transcribed_text = await gemini_engine.transcribe_voice(bytes(voice_bytes), mime_type="audio/ogg")
        await status_msg.delete()

        if not transcribed_text:
            if not gemini_engine.is_available:
                await update.message.reply_text(
                    "🎙️ *Fitur Voice Note Siap Digunakan!*\n\n"
                    "Untuk mengaktifkan transkripsi suara otomatis 100% gratis, dapatkan **Google Gemini API Key** "
                    "di [Google AI Studio](https://aistudio.google.com/) lalu masukkan `GEMINI_API_KEY` pada file `.env`!",
                    parse_mode="Markdown",
                )
                return
            else:
                await update.message.reply_text("⚠️ Suara tidak terdeteksi dengan jelas. Silakan coba rekam ulang atau ketik melalui teks.")
                return

        await update.message.reply_text(f"🎙️ *Suara Terdeteksi:* _{transcribed_text}_", parse_mode="Markdown")

        # Forward transcribed text to multi-item processor
        update.message.text = transcribed_text
        await handle_text_message(update, context)

    except Exception as e:
        logger.error("Error processing voice message: %s", e, exc_info=True)
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text("⚠️ Terjadi kendala saat memproses voice note.")


@restricted
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle interactive inline keyboard clicks."""
    query = update.callback_query
    await query.answer()
    data = query.data

    user_id = update.effective_user.id
    user_settings = await get_storage().get_user_settings(user_id)
    currency = user_settings.currency

    # --- 1-Click Undo Action ---
    if data.startswith("tx_undo:"):
        tx_id = data.split(":")[1]
        success, msg, _ = await financial_engine.revert_transaction(tx_id=tx_id, user_id=user_id)
        await query.edit_message_text(msg, parse_mode="Markdown")

    # --- Goals Callbacks ---
    elif data.startswith("goal_view:"):
        goal_id = data.split(":")[1]
        g = await get_storage().get_goal_by_id(goal_id, user_id)
        if g:
            status_str = "🎉 Selesai" if g.is_completed else f"{render_progress_bar(g.percentage_achieved)}"
            await query.message.reply_text(
                f"🎯 *DETAIL TARGET: {g.name}*\n\n"
                f"• Target: `{format_currency(g.target_amount, currency)}`\n"
                f"• Terkumpul: `{format_currency(g.current_amount, currency)}`\n"
                f"• Alokasi: `{g.allocation_percent}% per fee masuk`\n"
                f"• Progress: {status_str}\n"
                f"• ID: `{g.id}`",
                parse_mode="Markdown",
            )

    elif data.startswith("goal_del:"):
        goal_id = data.split(":")[1]
        await get_storage().delete_goal(goal_id, user_id)
        await query.edit_message_text(f"✅ Target `{goal_id}` berhasil dihapus.")

    elif data.startswith("goal_help:"):
        guide = (
            "💡 *Format Tambah Target:* `/add_goal <Nama> <Nominal> <Persen>`\n\n"
            "Contoh: `/add_goal Macbook M3 20jt 10%`"
        )
        await query.message.reply_text(guide, parse_mode="Markdown")

    # --- Subscriptions Callbacks ---
    elif data.startswith("sub_toggle:"):
        sub_id = data.split(":")[1]
        sub = await get_storage().get_subscription_by_id(sub_id, user_id)
        if sub:
            sub.is_active = not sub.is_active
            await get_storage().update_subscription(sub)
            state_str = "diaktifkan kembali" if sub.is_active else "dinonaktifkan sementara"
            await query.edit_message_text(f"✅ Langganan *{sub.name}* telah {state_str}.", parse_mode="Markdown")

    elif data.startswith("sub_del:"):
        sub_id = data.split(":")[1]
        await get_storage().delete_subscription(sub_id, user_id)
        await query.edit_message_text(f"✅ Langganan `{sub_id}` berhasil dihapus.")

    elif data.startswith("sub_help:"):
        guide = (
            "💡 *Format Tambah Langganan:* `/add_sub <Nama> <Nominal> <Tgl>`\n\n"
            "Contoh: `/add_sub ChatGPT Plus 300rb 15`"
        )
        await query.message.reply_text(guide, parse_mode="Markdown")

    # --- Daily Check-In Actions ---
    elif data.startswith("checkin:"):
        action = data.split(":")[1]
        if action == "record":
            guide = (
                "💡 *Contoh Format Cepat Pencatatan:*\n\n"
                "• *Satu Item:* `Makan warteg 20k`\n"
                "• *Banyak Item Sekaligus:* `Beli pensil 5rb, makan siang 20rb, bensin 25rb`\n"
                "• *Pemasukan:* `Dapat fee freelance 2jt`\n"
                "• 🎙️ *Voice Note:* Tahan tombol mic dan sebutkan pengeluaran Anda!"
            )
            await query.message.reply_text(guide, parse_mode="Markdown")
        elif action == "zero":
            await query.message.reply_text("🎉 *Luar Biasa!* Pengeluaran hari ini Rp0 (Hemat Maksimal!). Pertahankan kedisiplinan keuangan Anda! 🌟", parse_mode="Markdown")
        elif action == "status":
            await cmd_status(update, context)

    # --- Invoice Actions ---
    elif data.startswith("inv_pay:"):
        invoice_id = data.split(":")[1]
        success, msg, _ = await piutang_tracker.settle_invoice_payment(user_id=user_id, invoice_id=invoice_id)
        await query.message.reply_text(msg, parse_mode="Markdown")

    elif data.startswith("inv_remind:"):
        invoice_id = data.split(":")[1]
        success, msg = await piutang_tracker.generate_reminder_template(user_id=user_id, invoice_id=invoice_id)
        await query.message.reply_text(msg, parse_mode="Markdown")

    # --- Quotation Callbacks ---
    elif data.startswith("quote_pdf:"):
        quote_id = data.split(":")[1]
        q = await get_storage().get_quotation_by_id(quote_id, user_id)
        if q:
            pdf_bytes = quotation_generator.generate_pdf(q, user_settings)
            filename = f"SPH_{q.id}_{q.client_name.replace(' ', '_')}.pdf"
            await query.message.reply_document(
                document=io.BytesIO(pdf_bytes),
                filename=filename,
                caption=f"📄 *DOKUMEN PDF SPH: {q.id}*\n🏢 Klien: *{q.client_name}*\n💰 Nilai: *{format_currency(q.amount, currency)}*",
                parse_mode="Markdown",
            )

    elif data.startswith("quote_convert:"):
        quote_id = data.split(":")[1]
        q = await get_storage().get_quotation_by_id(quote_id, user_id)
        if q:
            due_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
            inv_items = [
                InvoiceItem(
                    description=it.description,
                    quantity=it.quantity,
                    rate=it.rate,
                    amount=it.amount,
                ) for it in q.items
            ] if q.items else [
                InvoiceItem(description=q.project_title, quantity=1.0, rate=q.amount, amount=q.amount)
            ]
            inv_create = InvoiceCreate(
                user_id=user_id,
                client_name=q.client_name,
                client_email=q.client_email,
                project_title=q.project_title,
                amount=q.amount,
                currency=q.currency,
                issue_date=datetime.now().strftime("%Y-%m-%d"),
                due_date=due_date,
                status=InvoiceStatus.UNPAID,
                items=inv_items,
                notes=f"Dikonversi otomatis dari Penawaran {q.id}.",
            )
            created_inv = await get_storage().add_invoice(inv_create)
            await get_storage().update_quotation_status(q.id, user_id, QuotationStatus.ACCEPTED, created_inv.id)

            pdf_bytes = invoice_generator.generate_pdf(created_inv, user_settings)
            await query.edit_message_text(
                f"🎉 *PENAWARAN DITERIMA & DIKONVERSI KE INVOICE!*\n\n"
                f"• No. SPH: `{q.id}` ➔ *ACCEPTED*\n"
                f"• No. Invoice: `{created_inv.id}`\n"
                f"• Total: `{format_currency(created_inv.amount, currency)}`",
                parse_mode="Markdown",
            )
            await query.message.reply_document(
                document=io.BytesIO(pdf_bytes),
                filename=f"Invoice_{created_inv.id}.pdf",
                caption=f"🧾 *Invoice Resmi {created_inv.id}* siap dikirimkan ke klien!",
                parse_mode="Markdown",
                reply_markup=get_invoice_action_keyboard(created_inv.id),
            )

    elif data.startswith("quote_del:"):
        quote_id = data.split(":")[1]
        await get_storage().delete_quotation(quote_id, user_id)
        await query.edit_message_text(f"✅ Penawaran `{quote_id}` berhasil dihapus.")

    elif data.startswith("quote_view:"):
        quote_id = data.split(":")[1]
        q = await get_storage().get_quotation_by_id(quote_id, user_id)
        if q:
            await query.message.reply_text(
                f"📄 *DETAIL SPH: {q.id}*\n\n"
                f"• Klien: *{q.client_name}*\n"
                f"• Proyek: *{q.project_title}*\n"
                f"• Total: `{format_currency(q.amount, currency)}`\n"
                f"• Durasi: `{q.timeline}`\n"
                f"• Masa Berlaku: `{q.valid_until}`\n"
                f"• Status: *{q.status.value}*",
                parse_mode="Markdown",
                reply_markup=get_quotation_action_keyboard(q.id),
            )

    elif data.startswith("quote_help:"):
        await query.message.reply_text(
            "💡 *Format Tambah Penawaran (SPH):*\n`/quote <Klien> | <Proyek> | <Nominal> | <Durasi>`\n\nContoh: `/quote PT Maju Jaya | Redesign Web | 15jt | 14 Hari Kerja`",
            parse_mode="Markdown",
        )

    # --- Termin Callbacks ---
    elif data.startswith("termin_inv:"):
        termin_id = data.split(":")[1]
        t = await get_storage().get_termin_by_id(termin_id, user_id)
        if t:
            # Find first un-invoiced milestone
            target_m = None
            for m in t.milestones:
                if m.status == MilestoneStatus.PENDING:
                    target_m = m
                    break
            if not target_m:
                await query.message.reply_text("Semua tahapan termin pada proyek ini sudah ditagihkan.")
                return

            created_inv, msg = await termin_tracker.create_invoice_for_milestone(t, target_m.id, get_storage())
            if created_inv:
                pdf_bytes = invoice_generator.generate_pdf(created_inv, user_settings)
                await query.message.reply_text(f"✅ {msg}", parse_mode="Markdown")
                await query.message.reply_document(
                    document=io.BytesIO(pdf_bytes),
                    filename=f"Invoice_{created_inv.id}.pdf",
                    caption=f"🧾 *Invoice {created_inv.id}* untuk *{target_m.title}* ({format_currency(target_m.amount, currency)})",
                    parse_mode="Markdown",
                    reply_markup=get_invoice_action_keyboard(created_inv.id),
                )
            else:
                await query.message.reply_text(f"⚠️ {msg}")

    elif data.startswith("termin_del:"):
        termin_id = data.split(":")[1]
        await get_storage().delete_termin(termin_id, user_id)
        await query.edit_message_text(f"✅ Proyek termin `{termin_id}` berhasil dihapus.")

    elif data.startswith("termin_view:"):
        termin_id = data.split(":")[1]
        t = await get_storage().get_termin_by_id(termin_id, user_id)
        if t:
            card_text = termin_tracker.render_termin_card(t)
            await query.message.reply_text(
                card_text,
                parse_mode="Markdown",
                reply_markup=get_termin_action_keyboard(t.id),
            )

    elif data.startswith("termin_help:"):
        await query.message.reply_text(
            "💡 *Format Tambah Proyek Termin:*\n`/termin <Klien> | <Proyek> | <Total Nilai> | <Persentase Termin>`\n\nContoh: `/termin PT Maju Jaya | Redesign Website | 15jt | 50% 30% 20%`",
            parse_mode="Markdown",
        )

    # --- Tax Callbacks ---
    elif data.startswith("tax_pdf:"):
        await cmd_export_spt(update, context)

    elif data.startswith("tax_ptkp:"):
        await query.message.reply_text(
            "👤 *PILIH STATUS PTKP ANDA:*\n\n"
            "• *TK/0:* Lajang tanpa tanggungan (Rp 54 Juta)\n"
            "• *TK/1:* Lajang 1 tanggungan (Rp 58.5 Juta)\n"
            "• *K/0:* Menikah tanpa tanggungan (Rp 58.5 Juta)\n"
            "• *K/1:* Menikah 1 anak/tanggungan (Rp 63 Juta)\n"
            "• *K/2:* Menikah 2 anak/tanggungan (Rp 67.5 Juta)\n"
            "• *K/3:* Menikah 3 anak/tanggungan (Rp 72 Juta)",
            parse_mode="Markdown",
            reply_markup=get_ptkp_selection_keyboard(),
        )

    elif data.startswith("ptkp_set:"):
        ptkp_key = data.split(":")[1]
        try:
            ptkp_enum = PTKPStatus[ptkp_key]
            user_settings.ptkp_status = ptkp_enum
            await get_storage().update_user_settings(user_settings)
            await query.edit_message_text(f"✅ Status PTKP berhasil diubah menjadi *{ptkp_enum.value}*.", parse_mode="Markdown")
            await cmd_pajak(update, context)
        except Exception as e:
            logger.error("Failed to update PTKP: %s", e)

    # --- Currency Callbacks ---
    elif data.startswith("curr_refresh:"):
        rates_card = await currency_converter.render_rates_table()
        await query.edit_message_text(
            rates_card,
            parse_mode="Markdown",
            reply_markup=get_currency_keyboard(),
        )

    elif data.startswith("curr_help:"):
        help_text = (
            "💡 *Contoh Format Konversi Valas:*\n"
            "• `/convert 500 USD to IDR`\n"
            "• `/convert 450 USD upwork` _(Auto-hitung fee 10%)_\n"
            "• `/convert 1200 SGD`\n"
            "• `/convert 250 EUR paypal`\n"
            "• `/convert 500 USDT`"
        )
        await query.message.reply_text(help_text, parse_mode="Markdown")

    # --- Transaction Confirmation Actions ---
    elif data.startswith("tx_confirm:"):
        pending_id = data.split(":")[1]
        pending_data = context.user_data.get(f"pending_tx_{pending_id}")
        if not pending_data:
            await query.edit_message_text("⚠️ Data transaksi sudah kedaluwarsa atau telah diproses.")
            return

        tx_create = TransactionCreate(
            user_id=user_id,
            timestamp=datetime.fromisoformat(pending_data["timestamp"]),
            type=TransactionType(pending_data["type"]),
            category=Category(pending_data["category"]),
            amount=float(pending_data["amount"]),
            source_or_merchant=pending_data["source_or_merchant"],
            notes=pending_data.get("notes", ""),
        )

        if tx_create.type == TransactionType.INCOME:
            persisted_tx, split_result = await financial_engine.process_income(tx_create)
            await query.edit_message_text(
                f"✅ *Struk Tersimpan!*\n\n{split_result.message}",
                parse_mode="Markdown",
                reply_markup=get_undo_keyboard(persisted_tx.id),
            )
        else:
            persisted_tx, guard_result = await financial_engine.process_expense(tx_create)
            status_icon = "🚨" if guard_result.status == BudgetGuardStatus.BREACH else ("⚠️" if guard_result.status == BudgetGuardStatus.WARNING else "✅")
            resp = (
                f"{status_icon} *STRUK BERHASIL DISIMPAN*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"💸 *Nominal:* `{format_currency(tx_create.amount, currency)}`\n"
                f"📂 *Kategori:* *{tx_create.category.value}*\n"
                f"🏢 *Merchant:* `{tx_create.source_or_merchant}`\n\n"
                f"{guard_result.message}"
            )
            await query.edit_message_text(
                resp,
                parse_mode="Markdown",
                reply_markup=get_undo_keyboard(persisted_tx.id),
            )

        context.user_data.pop(f"pending_tx_{pending_id}", None)

    elif data.startswith("tx_cat_menu:"):
        pending_id = data.split(":")[1]
        await query.edit_message_reply_markup(reply_markup=get_category_picker_keyboard(pending_id))

    elif data.startswith("tx_set_cat:"):
        parts = data.split(":")
        pending_id = parts[1]
        new_cat = parts[2]
        pending_data = context.user_data.get(f"pending_tx_{pending_id}")
        if pending_data:
            pending_data["category"] = new_cat
            await query.edit_message_text(
                f"🧾 *PREVIEW STRUK AI OCR*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏪 *Merchant:* `{pending_data['source_or_merchant']}`\n"
                f"💰 *Nominal:* `{format_currency(float(pending_data['amount']), currency)}`\n"
                f"📂 *Kategori:* *{new_cat}* (Diperbarui)\n"
                f"🔖 *Tipe:* *{pending_data['type']}*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"Silakan konfirmasi penyimpanan:",
                parse_mode="Markdown",
                reply_markup=get_confirmation_keyboard(pending_id),
            )

    elif data.startswith("tx_back:"):
        pending_id = data.split(":")[1]
        await query.edit_message_reply_markup(reply_markup=get_confirmation_keyboard(pending_id))

    elif data.startswith("tx_cancel:"):
        pending_id = data.split(":")[1]
        context.user_data.pop(f"pending_tx_{pending_id}", None)
        await query.edit_message_text("❌ Pencatatan transaksi dibatalkan.")


async def scheduled_daily_checkin(app: Application) -> None:
    """Scheduled daily evening reminder sent at configured hour (e.g. 21:00)."""
    logger.info("Executing scheduled daily evening check-in...")
    users = settings.allowed_users
    if not users:
        return

    for uid in users:
        try:
            safe_info = await financial_engine.get_daily_safe_spend(uid)
            currency = safe_info["currency"]
            today_spent = safe_info["today_spent"]
            daily_limit = safe_info["daily_safe_limit"]

            checkin_msg = (
                f"🌙 *DAILY EVENING CHECK-IN*\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"Halo! Ada pengeluaran atau pemasukan yang belum sempat dicatat hari ini?\n\n"
                f"📊 *Pengeluaran Hari Ini:* `{format_currency(today_spent, currency)}`\n"
                f"🎯 *Batas Aman Harian:* `{format_currency(daily_limit, currency)}/hari` (Sisa {safe_info['days_remaining']} hari)\n\n"
                f"Silakan ketik transaksi Anda, kirim voice note 🎙️, atau gunakan tombol di bawah:"
            )
            await app.bot.send_message(
                chat_id=uid,
                text=checkin_msg,
                parse_mode="Markdown",
                reply_markup=get_daily_checkin_keyboard(),
            )
            logger.info("Sent daily check-in to user_id: %s", uid)
        except Exception as e:
            logger.error("Failed to send daily check-in to user_id %s: %s", uid, e)


async def scheduled_subscription_reminder(app: Application) -> None:
    """Check upcoming subscriptions in the next 3 days and notify users."""
    logger.info("Checking upcoming subscription bills due...")
    users = settings.allowed_users
    if not users:
        return

    now_day = datetime.now().day
    storage = get_storage()

    for uid in users:
        try:
            subs = await storage.get_subscriptions(uid, is_active=True)
            user_settings = await storage.get_user_settings(uid)
            currency = user_settings.currency

            near_subs = []
            for s in subs:
                days_left = (s.billing_day - now_day) if s.billing_day >= now_day else (30 - now_day + s.billing_day)
                if 0 <= days_left <= 3:
                    near_subs.append((s, days_left))

            if near_subs:
                lines = []
                for s, d in near_subs:
                    due_label = "HARI INI! 🚨" if d == 0 else f"{d} hari lagi (Tgl {s.billing_day})"
                    lines.append(f"• *{s.name}:* `{format_currency(s.amount, currency)}` — _{due_label}_")

                msg = (
                    f"🔔 *PENGINGAT TAGIHAN RUTIN DEKAT*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"Berikut tagihan langganan yang akan jatuh tempo dalam 3 hari ke depan:\n\n"
                    + "\n".join(lines) + "\n\n"
                    f"Pastikan saldo di rekening pembayaran Anda mencukupi!"
                )
                await app.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
                logger.info("Sent subscription reminder to user_id: %s", uid)
        except Exception as e:
            logger.error("Failed to check subscriptions for user %s: %s", uid, e)

