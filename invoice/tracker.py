"""
Client Piutang (Receivables) and Payment Tracker Module.
Manages unpaid invoice monitoring, automated reminder templates, and settlement flow into Income Smoothing Engine.
"""

import logging
from datetime import datetime, date
from typing import List, Optional, Tuple, Dict, Any

from config import format_currency
from database.base import StorageBackend
from database import get_storage
from database.models import (
    Invoice,
    InvoiceStatus,
    TransactionCreate,
    TransactionType,
    Category,
    IncomeSplitResult,
)
from engine.financial_engine import FreelanceFinancialEngine, financial_engine

logger = logging.getLogger(__name__)


class PiutangTracker:
    def __init__(self, storage: Optional[StorageBackend] = None, engine: Optional[FreelanceFinancialEngine] = None):
        self.storage = storage or get_storage()
        self.engine = engine or financial_engine

    @staticmethod
    def get_days_remaining(due_date_str: str) -> int:
        """Calculate days remaining until due date. Negative means overdue."""
        try:
            due_dt = datetime.strptime(due_date_str, "%Y-%m-%d").date()
            today = datetime.now().date()
            return (due_dt - today).days
        except Exception:
            return 0

    async def get_unpaid_invoices_summary(self, user_id: int) -> Tuple[str, List[Invoice]]:
        """Get formatted list of all unpaid client invoices with due status badges."""
        invoices = await self.storage.get_invoices(user_id=user_id, status=InvoiceStatus.UNPAID)
        user_settings = await self.storage.get_user_settings(user_id)
        currency = user_settings.currency

        if not invoices:
            msg = (
                "🎉 *TIDAK ADA PIUTANG KLIEN MENUNGGAK!*\n"
                "Semua invoice Anda telah lunas atau belum ada invoice baru yang dibuat.\n"
                "Ketik `/invoice` untuk membuat invoice tagihan baru."
            )
            return msg, []

        total_piutang = sum(inv.amount for inv in invoices)
        lines = [
            f"⏰ *DAFTAR PIUTANG & INVOICE BELUM LUNAS*\n"
            f"Total Piutang Tertagih: *{format_currency(total_piutang, currency)}* ({len(invoices)} Invoice)\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        ]

        for i, inv in enumerate(invoices, start=1):
            days_left = self.get_days_remaining(inv.due_date)
            if days_left < 0:
                badge = f"🔴 *TERLAMBAT {abs(days_left)} HARI*"
            elif days_left == 0:
                badge = "🟡 *JATUH TEMPO HARI INI*"
            elif days_left <= 3:
                badge = f"🟠 *H-{days_left} Hari Lagi*"
            else:
                badge = f"🟢 *H-{days_left} Hari*"

            lines.append(
                f"{i}. `{inv.id}` — *{inv.client_name}*\n"
                f"   💰 *{format_currency(inv.amount, inv.currency)}* | {badge}\n"
                f"   📁 _{inv.project_title}_\n"
                f"   📅 Tempo: `{inv.due_date}`\n"
                f"   👉 Tandai Lunas: `/pay_invoice {inv.id}`\n"
                f"   👉 Pesan Tagihan: `/remind_invoice {inv.id}`\n"
            )

        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 *Tips:* Saat klien mentransfer, ketik `/pay_invoice <ID>` agar dana otomatis dialokasikan ke gaji & Buffer Fund!")
        return "\n".join(lines), invoices

    async def settle_invoice_payment(
        self,
        user_id: int,
        invoice_id: str,
    ) -> Tuple[bool, str, Optional[IncomeSplitResult]]:
        """
        Mark invoice as PAID and automatically route funds into the Freelance Income Splitter!
        """
        invoice = await self.storage.get_invoice_by_id(invoice_id, user_id)
        if not invoice:
            return False, f"Invoice dengan ID `{invoice_id}` tidak ditemukan.", None

        if invoice.status == InvoiceStatus.PAID:
            return False, f"Invoice `{invoice.id}` sudah berstatus LUNAS sebelumnya.", None

        # 1. Update Invoice Status
        await self.storage.update_invoice_status(invoice.id, user_id, InvoiceStatus.PAID)

        # 2. Automatically Feed into Income Smoothing Engine!
        tx_create = TransactionCreate(
            user_id=user_id,
            timestamp=datetime.now(),
            type=TransactionType.INCOME,
            category=Category.BUFFER,
            amount=invoice.amount,
            source_or_merchant=f"Klien: {invoice.client_name}",
            notes=f"Pelunasan Invoice {invoice.id} ({invoice.project_title})",
        )

        persisted_tx, split_result = await self.engine.process_income(tx_create)

        msg = (
            f"🎉 *INVOICE DILUNASI & INCOME DIPROSES*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🧾 *No. Invoice:* `{invoice.id}`\n"
            f"🏢 *Klien:* `{invoice.client_name}`\n"
            f"📁 *Proyek:* `{invoice.project_title}`\n\n"
            f"{split_result.message}"
        )
        return True, msg, split_result

    async def generate_reminder_template(
        self,
        user_id: int,
        invoice_id: str,
    ) -> Tuple[bool, str]:
        """
        Generate a polite, professional payment reminder message ready to copy-paste into WhatsApp or Email.
        """
        invoice = await self.storage.get_invoice_by_id(invoice_id, user_id)
        if not invoice:
            return False, f"Invoice dengan ID `{invoice_id}` tidak ditemukan."

        user_settings = await self.storage.get_user_settings(user_id)
        freelancer_name = user_settings.freelancer_name or "Saya"
        currency = invoice.currency
        days_left = self.get_days_remaining(invoice.due_date)

        if days_left < 0:
            urgency_text = f"telah melewati tanggal jatuh tempo ({invoice.due_date})"
        elif days_left == 0:
            urgency_text = "jatuh tempo pada hari ini"
        else:
            urgency_text = f"akan jatuh tempo pada tanggal {invoice.due_date}"

        payment_details = user_settings.payment_details or "BCA: 123-456-7890 a/n Freelancer"

        wa_draft = (
            f"💬 *DRAFT PESAN PENGINGAT TAGIHAN (WHATSAPP/EMAIL)*\n"
            f"_(Tinggal Salin & Kirim ke Klien)_\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Halo Rekan *{invoice.client_name}*,\n\n"
            f"Semoga dalam keadaan sehat selalu.\n\n"
            f"Melalui pesan ini, saya ingin menginformasikan terkait tagihan untuk pekerjaan *{invoice.project_title}* dengan rincian berikut:\n\n"
            f"• *No. Invoice:* {invoice.id}\n"
            f"• *Total Tagihan:* {format_currency(invoice.amount, currency)}\n"
            f"• *Jatuh Tempo:* {invoice.due_date} ({urgency_text})\n\n"
            f"Pembayaran dapat disalurkan melalui:\n"
            f"*{payment_details}*\n\n"
            f"Jika sudah melakukan pembayaran, mohon konfirmasi bukti transfernya ya. Terima kasih banyak atas kerja sama yang baik!\n\n"
            f"Salam hangat,\n"
            f"*{freelancer_name}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
        return True, wa_draft


piutang_tracker = PiutangTracker()
