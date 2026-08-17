"""
Quotation text parser for conversational and piped commands.
"""

import re
import logging
from typing import Optional, List
from datetime import datetime, timedelta

from database.models import QuotationCreate, QuotationItem, QuotationStatus
from ai.nlp_parser import NLPParser

logger = logging.getLogger(__name__)


class QuotationParser:
    """Parses text commands for creating Quotation / SPH."""

    @staticmethod
    def parse_command_text(text: str, user_id: int) -> Optional[QuotationCreate]:
        """
        Parses piped or conversational quotation command.
        Formats:
        - /quote PT Maju Jaya | Redesign Website | 10jt | 14 Hari Kerja
        - /quote Klien: PT ABC, Proyek: Landing Page, Total: 5jt, Durasi: 1 minggu
        """
        clean = text.strip()
        for cmd in ["/quote", "/penawaran", "/sph"]:
            if clean.lower().startswith(cmd):
                clean = clean[len(cmd):].strip()
                break

        if not clean:
            return None

        # Piped format: Client | Project | Amount | Timeline | DP Terms
        if "|" in clean:
            parts = [p.strip() for p in clean.split("|")]
            if len(parts) < 3:
                return None

            client_name = parts[0]
            project_title = parts[1]
            amount_str = parts[2]
            timeline = parts[3] if len(parts) > 3 else "14 Hari Kerja"
            dp_terms = parts[4] if len(parts) > 4 else "Down Payment 50% sebelum mulai"
            revision_limit = parts[5] if len(parts) > 5 else "Maksimal 2x Revisi Minor"

            amount = NLPParser._parse_indonesian_number(amount_str)
            if amount <= 0:
                amount = 1_000_000.0

            valid_until = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
            issue_date = datetime.now().strftime("%Y-%m-%d")

            item = QuotationItem(
                description=f"Jasa Pengerjaan {project_title}",
                quantity=1.0,
                rate=amount,
                amount=amount,
            )

            return QuotationCreate(
                user_id=user_id,
                client_name=client_name,
                project_title=project_title,
                amount=amount,
                currency="IDR",
                issue_date=issue_date,
                valid_until=valid_until,
                timeline=timeline,
                revision_limit=revision_limit,
                dp_terms=dp_terms,
                status=QuotationStatus.SENT,
                items=[item],
                notes="Pengerjaan dimulai H+1 setelah konfirmasi DP diterima.",
            )

        # Fallback simpler format: /quote <Client> <Nominal>
        parts = clean.split()
        if len(parts) >= 2:
            amount = NLPParser._parse_indonesian_number(parts[-1])
            if amount > 0:
                client_name = " ".join(parts[:-1])
                valid_until = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
                issue_date = datetime.now().strftime("%Y-%m-%d")
                project_title = f"Proyek Layanan Freelance untuk {client_name}"
                item = QuotationItem(
                    description=project_title,
                    quantity=1.0,
                    rate=amount,
                    amount=amount,
                )
                return QuotationCreate(
                    user_id=user_id,
                    client_name=client_name,
                    project_title=project_title,
                    amount=amount,
                    currency="IDR",
                    issue_date=issue_date,
                    valid_until=valid_until,
                    timeline="14 Hari Kerja",
                    revision_limit="Maksimal 2x Revisi Minor",
                    dp_terms="Down Payment 50% sebelum mulai",
                    status=QuotationStatus.SENT,
                    items=[item],
                )

        return None


quotation_parser = QuotationParser()
