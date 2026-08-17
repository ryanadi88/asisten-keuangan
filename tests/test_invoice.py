"""
Unit tests for PDF Invoice Generator, Parser, and Reminder Templates.
"""

import pytest
from datetime import datetime

from database.sqlite_db import SQLiteBackend
from database.models import InvoiceCreate, InvoiceItem, InvoiceStatus, UserSettings
from invoice.invoice_generator import invoice_generator
from invoice.invoice_parser import invoice_parser
from invoice.tracker import piutang_tracker


@pytest.mark.asyncio
async def test_invoice_parser_pipe_syntax():
    text = "Klien: PT Maju Digital | Project: Redesign Website UI | Nominal: 8.5jt | Due: 14 hari | Email: finance@ptmaju.com"
    inv_create = invoice_parser.parse_invoice_text(text, user_id=301)

    assert inv_create.client_name == "PT Maju Digital"
    assert inv_create.project_title == "Redesign Website UI"
    assert inv_create.amount == 8_500_000.0
    assert inv_create.client_email == "finance@ptmaju.com"
    assert inv_create.status == InvoiceStatus.UNPAID
    assert len(inv_create.items) == 1
    assert inv_create.items[0].amount == 8_500_000.0


@pytest.mark.asyncio
async def test_invoice_pdf_rendering(tmp_path):
    db_path = str(tmp_path / "test_inv_pdf.db")
    storage = SQLiteBackend(db_path=db_path)
    await storage.init_db()

    user_id = 302
    inv_create = invoice_parser.parse_invoice_text(
        "Klien: Acme Studio | Project: Backend API | Nominal: 12000000 | Due: 7 hari",
        user_id=user_id,
    )
    persisted_inv = await storage.add_invoice(inv_create)
    user_settings = await storage.get_user_settings(user_id)

    pdf_bytes = invoice_generator.generate_pdf(persisted_inv, user_settings)
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF")  # Valid PDF header magic bytes


@pytest.mark.asyncio
async def test_reminder_template_generation(tmp_path):
    db_path = str(tmp_path / "test_remind.db")
    storage = SQLiteBackend(db_path=db_path)
    await storage.init_db()
    tracker = piutang_tracker
    tracker.storage = storage

    user_id = 303
    inv_create = InvoiceCreate(
        user_id=user_id,
        client_name="PT Gemilang",
        client_email="info@gemilang.com",
        project_title="Konsultasi IT",
        amount=5_000_000.0,
        currency="IDR",
        issue_date="2026-08-01",
        due_date="2026-08-15",
        status=InvoiceStatus.UNPAID,
    )
    inv = await storage.add_invoice(inv_create)

    success, reminder_msg = await tracker.generate_reminder_template(user_id=user_id, invoice_id=inv.id)
    assert success is True
    assert "PT Gemilang" in reminder_msg
    assert inv.id in reminder_msg
    assert "5.000.000" in reminder_msg
