"""
Project Termin & Milestone Tracker Engine for Freelancers.
Manages multi-phase payments (e.g. DP 50%, Review 30%, Final 20%) and generates invoices per milestone.
"""

import uuid
import logging
from typing import Optional, List, Tuple
from datetime import datetime, timedelta

from config import format_currency
from database.base import StorageBackend
from database.models import (
    ProjectTermin,
    ProjectTerminCreate,
    ProjectMilestone,
    MilestoneStatus,
    Invoice,
    InvoiceCreate,
    InvoiceItem,
    InvoiceStatus,
)
from ai.nlp_parser import NLPParser

logger = logging.getLogger(__name__)


class TerminTracker:
    """Handles project termin milestone creation, invoice generation, and status updates."""

    @staticmethod
    def parse_termin_command(text: str, user_id: int) -> Optional[ProjectTerminCreate]:
        """
        Parse piped or space-separated command into ProjectTerminCreate.
        Formats:
        - /termin PT Maju Jaya | Redesign Web | 15jt | 50% 30% 20%
        - /termin PT Maju Jaya | Mobile App | 20.000.000 | 50 25 25
        - /termin Klien XYZ 10jt
        """
        clean = text.strip()
        for cmd in ["/termin", "/milestone", "/dp"]:
            if clean.lower().startswith(cmd):
                clean = clean[len(cmd):].strip()
                break

        if not clean:
            return None

        client_name = "Klien Freelance"
        project_title = "Proyek Freelance"
        total_amount = 0.0
        splits = [50.0, 50.0]  # Default 50% DP, 50% Final

        if "|" in clean:
            parts = [p.strip() for p in clean.split("|")]
            if len(parts) >= 2:
                client_name = parts[0]
                project_title = parts[1]
            if len(parts) >= 3:
                total_amount = NLPParser._parse_indonesian_number(parts[2])
            if len(parts) >= 4:
                # Custom split percentages: "50% 30% 20%" or "50, 30, 20"
                raw_splits = parts[3].replace(",", " ").replace("%", " ").split()
                parsed_splits = []
                for s in raw_splits:
                    try:
                        v = float(s)
                        if v > 0:
                            parsed_splits.append(v)
                    except ValueError:
                        pass
                if parsed_splits and sum(parsed_splits) == 100.0:
                    splits = parsed_splits
                elif parsed_splits:
                    # Normalize if doesn't sum exactly to 100
                    total_s = sum(parsed_splits)
                    splits = [round((v / total_s) * 100.0, 1) for v in parsed_splits]
        else:
            parts = clean.split()
            if len(parts) >= 2:
                total_amount = NLPParser._parse_indonesian_number(parts[-1])
                client_name = " ".join(parts[:-1])
                project_title = f"Proyek {client_name}"

        if total_amount <= 0:
            return None

        # Build ProjectMilestone list
        milestones: List[ProjectMilestone] = []
        for idx, pct in enumerate(splits, start=1):
            m_amount = round((pct / 100.0) * total_amount, 2)
            if idx == 1:
                title = f"Termin 1 - DP ({pct:g}%)"
            elif idx == len(splits):
                title = f"Termin {idx} - Pelunasan Final ({pct:g}%)"
            else:
                title = f"Termin {idx} - Progres ({pct:g}%)"

            milestones.append(
                ProjectMilestone(
                    id=f"m{idx}",
                    title=title,
                    percentage=pct,
                    amount=m_amount,
                    status=MilestoneStatus.PENDING,
                )
            )

        return ProjectTerminCreate(
            user_id=user_id,
            client_name=client_name,
            project_title=project_title,
            total_amount=total_amount,
            currency="IDR",
            milestones=milestones,
            created_at=datetime.now().strftime("%Y-%m-%d"),
            is_completed=False,
        )

    @staticmethod
    async def create_invoice_for_milestone(
        termin: ProjectTermin,
        milestone_id: str,
        storage: StorageBackend,
    ) -> Tuple[Optional[Invoice], str]:
        """Generate official invoice for a specific termin milestone."""
        target_m: Optional[ProjectMilestone] = None
        for m in termin.milestones:
            if m.id == milestone_id or milestone_id.lower() in m.title.lower():
                target_m = m
                break

        if not target_m:
            return None, "Milestone tidak ditemukan."

        if target_m.status == MilestoneStatus.PAID:
            return None, f"Milestone '{target_m.title}' sudah berstatus LUNAS."

        # Create Invoice
        due_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        item = InvoiceItem(
            description=f"{termin.project_title} - {target_m.title}",
            quantity=1.0,
            rate=target_m.amount,
            amount=target_m.amount,
        )
        inv_create = InvoiceCreate(
            user_id=termin.user_id,
            client_name=termin.client_name,
            project_title=f"{termin.project_title} ({target_m.title})",
            amount=target_m.amount,
            currency=termin.currency,
            issue_date=datetime.now().strftime("%Y-%m-%d"),
            due_date=due_date,
            status=InvoiceStatus.UNPAID,
            items=[item],
            notes=f"Penagihan bertahap untuk proyek '{termin.project_title}'.",
        )
        created_invoice = await storage.add_invoice(inv_create)

        # Update milestone in termin
        target_m.status = MilestoneStatus.INVOICED
        target_m.invoice_id = created_invoice.id
        await storage.update_termin(termin)

        return created_invoice, f"Invoice {created_invoice.id} berhasil dibuat untuk {target_m.title}!"

    @staticmethod
    def render_termin_card(termin: ProjectTermin) -> str:
        """Format a project termin tracker into an attractive Telegram card."""
        currency = termin.currency
        lines = [
            f"⏳ *PROYEK TERMIN: {termin.project_title.upper()}*",
            f"━━━━━━━━━━━━━━━━━━━━━",
            f"🏢 Klien: *{termin.client_name}*",
            f"💰 Total Nilai Kontrak: *{format_currency(termin.total_amount, currency)}*",
            f"📅 Tanggal Dibuat: `{termin.created_at}`",
            f"ID Proyek: `{termin.id}`\n",
            f"📌 *Rincian Tahapan Termin:*",
        ]

        for m in termin.milestones:
            if m.status == MilestoneStatus.PAID:
                status_badge = "🟢 *LUNAS*"
            elif m.status == MilestoneStatus.INVOICED:
                status_badge = f"🟡 *DITAGIHKAN* (`{m.invoice_id or 'INV'}`)"
            else:
                status_badge = "⚪ *MENUNGGU*"

            lines.append(
                f"• *{m.title}* ({m.percentage:g}%)\n"
                f"  Nominal: `{format_currency(m.amount, currency)}` | Status: {status_badge}"
            )

        lines.append(f"━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"💵 Sudah Ditagih: `{format_currency(termin.total_billed, currency)}`")
        lines.append(f"🪙 Sisa Belum Ditagih: `*{format_currency(termin.total_unbilled, currency)}*`")

        if termin.is_completed:
            lines.append("🎉 *STATUS: PROYEK INI TELAH SELESAI 100% & LUNAS*")

        return "\n".join(lines)


termin_tracker = TerminTracker()
