"""
Parser module for creating invoices from Telegram conversational text or structured syntax.
"""

import re
from datetime import datetime, timedelta
from typing import Optional, List

from database.models import InvoiceCreate, InvoiceItem, InvoiceStatus
from ai.nlp_parser import nlp_parser


class InvoiceParser:
    """Parses text inputs into structured InvoiceCreate objects."""

    @staticmethod
    def parse_invoice_text(text: str, user_id: int) -> InvoiceCreate:
        """
        Parse text into InvoiceCreate.
        Supports structured pipe syntax:
        "Klien: PT Maju | Project: Web Landing | Nominal: 7.5jt | Due: 14 hari | Email: klien@ptmaju.com"
        """
        client_name = "Klien Terhormat"
        client_email = ""
        project_title = "Jasa Freelance & Pengembangan Solusi"
        amount = 0.0
        due_days = 14
        due_date_str = None
        notes = ""

        # 1. Pipe-delimited parsing
        if "|" in text:
            parts = text.split("|")
            for p in parts:
                p_clean = p.strip()
                p_lower = p_clean.lower()

                if any(p_lower.startswith(k) for k in ["klien:", "client:", "to:"]):
                    client_name = p_clean.split(":", 1)[1].strip()
                elif any(p_lower.startswith(k) for k in ["project:", "proyek:", "layanan:", "scope:"]):
                    project_title = p_clean.split(":", 1)[1].strip()
                elif any(p_lower.startswith(k) for k in ["nominal:", "amount:", "harga:", "total:"]):
                    val_str = p_clean.split(":", 1)[1].strip()
                    amount = nlp_parser._parse_amount_heuristic(val_str)
                elif any(p_lower.startswith(k) for k in ["due:", "tempo:", "jatuh tempo:"]):
                    due_val = p_clean.split(":", 1)[1].strip().lower()
                    # Check if 'X hari' or 'X days'
                    days_match = re.search(r"(\d+)\s*(?:hari|days|day|hr)", due_val)
                    if days_match:
                        due_days = int(days_match.group(1))
                    elif re.match(r"\d{4}-\d{2}-\d{2}", due_val):
                        due_date_str = due_val
                elif any(p_lower.startswith(k) for k in ["email:", "mail:"]):
                    client_email = p_clean.split(":", 1)[1].strip()
                elif any(p_lower.startswith(k) for k in ["notes:", "catatan:", "ket:"]):
                    notes = p_clean.split(":", 1)[1].strip()

        else:
            # Unstructured parsing
            amount = nlp_parser._parse_amount_heuristic(text)
            if amount == 0:
                amount = 5_000_000.0  # Default fallback

            # Try extracting client name
            klien_match = re.search(r"(?:klien|client|untuk|pt|cv)\s+([a-zA-Z0-9\s]+?)(?:project|proyek|nominal|sebesar|tempo|due|$)", text, re.IGNORECASE)
            if klien_match:
                client_name = klien_match.group(1).strip().title()

            # Try extracting project title
            project_match = re.search(r"(?:project|proyek|pembuatan|jasa|redesign)\s+([a-zA-Z0-9\s]+?)(?:nominal|sebesar|tempo|due|$)", text, re.IGNORECASE)
            if project_match:
                project_title = project_match.group(0).strip().title()

            days_match = re.search(r"(\d+)\s*(?:hari|days)", text, re.IGNORECASE)
            if days_match:
                due_days = int(days_match.group(1))

        # Calculate due date if not explicit
        if not due_date_str:
            due_date_dt = datetime.now() + timedelta(days=due_days)
            due_date_str = due_date_dt.strftime("%Y-%m-%d")

        if amount <= 0:
            amount = 5_000_000.0

        item = InvoiceItem(
            description=project_title,
            quantity=1.0,
            rate=amount,
            amount=amount,
        )

        return InvoiceCreate(
            user_id=user_id,
            client_name=client_name,
            client_email=client_email,
            project_title=project_title,
            amount=amount,
            currency="IDR",
            issue_date=datetime.now().strftime("%Y-%m-%d"),
            due_date=due_date_str,
            status=InvoiceStatus.UNPAID,
            items=[item],
            notes=notes,
        )


invoice_parser = InvoiceParser()
