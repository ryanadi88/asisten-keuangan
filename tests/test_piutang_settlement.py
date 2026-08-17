"""
Unit tests for Client Piutang Settlement & Income Smoothing Integration.
"""

import pytest
from datetime import datetime

from database.sqlite_db import SQLiteBackend
from database.models import InvoiceCreate, InvoiceStatus, Category, TransactionType
from engine.financial_engine import FreelanceFinancialEngine
from invoice.tracker import PiutangTracker


@pytest.mark.asyncio
async def test_settle_invoice_payment_flow(tmp_path):
    """
    Test invoice settlement:
    1. Create Unpaid Invoice Rp 15,000,000 for PT Sukses
    2. Freelancer marks invoice as PAID via settle_invoice_payment
    3. Verify:
       - Invoice status becomes PAID
       - Income Splitter triggered:
         - Tax Reserve 10% = 1,500,000
         - Base Salary Allocated = 10,000,000 (Target met)
         - Buffer Pool Surplus = 3,500,000
    """
    db_path = str(tmp_path / "test_piutang_flow.db")
    storage = SQLiteBackend(db_path=db_path)
    await storage.init_db()

    engine = FreelanceFinancialEngine(storage=storage)
    tracker = PiutangTracker(storage=storage, engine=engine)

    user_id = 401
    month_year = datetime.now().strftime("%Y-%m")

    # 1. Create Invoice
    inv_create = InvoiceCreate(
        user_id=user_id,
        client_name="PT Sukses Abadi",
        project_title="Fullstack Web Application",
        amount=15_000_000.0,
        due_date="2026-08-30",
        status=InvoiceStatus.UNPAID,
    )
    inv = await storage.add_invoice(inv_create)
    assert inv.status == InvoiceStatus.UNPAID

    # 2. Settle Payment
    success, msg, split_result = await tracker.settle_invoice_payment(user_id=user_id, invoice_id=inv.id)
    assert success is True
    assert split_result is not None

    # Check Invoice status in DB
    updated_inv = await storage.get_invoice_by_id(inv.id, user_id)
    assert updated_inv.status == InvoiceStatus.PAID
    assert updated_inv.paid_date is not None

    # Check Income Splitter Result
    assert split_result.gross_income == 15_000_000.0
    assert split_result.tax_reserve_amount == 1_500_000.0  # 10%
    assert split_result.salary_drawn_allocated == 10_000_000.0  # Target salary
    assert split_result.salary_target_met is True
    assert split_result.buffer_pool_allocated == 3_500_000.0  # Surplus
    assert split_result.current_buffer_balance == 3_500_000.0

    # Verify Summary in DB
    summary = await storage.get_monthly_summary(month_year, user_id)
    assert summary.total_income == 15_000_000.0
    assert summary.actual_salary_drawn == 10_000_000.0
    assert summary.buffer_fund_balance == 3_500_000.0
    assert summary.tax_reserve == 1_500_000.0
