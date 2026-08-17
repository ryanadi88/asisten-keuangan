"""
Unit tests for Monthly Report and Matplotlib Chart Generator.
"""

import pytest
from datetime import datetime

from database.sqlite_db import SQLiteBackend
from database.models import TransactionCreate, TransactionType, Category
from engine.financial_engine import FreelanceFinancialEngine
from reporter.monthly_report import MonthlyReporter
from reporter.chart_generator import make_ascii_bar


@pytest.mark.asyncio
async def test_ascii_bar():
    assert "100%" in make_ascii_bar(100)
    assert "50%" in make_ascii_bar(50)
    assert "0%" in make_ascii_bar(0)


@pytest.mark.asyncio
async def test_monthly_reporter(tmp_path):
    db_path = str(tmp_path / "test_report.db")
    storage = SQLiteBackend(db_path=db_path)
    await storage.init_db()
    engine = FreelanceFinancialEngine(storage=storage)
    reporter = MonthlyReporter(storage=storage, engine=engine)

    user_id = 201
    month_year = "2026-08"

    # Add Income
    tx_inc = TransactionCreate(
        user_id=user_id,
        timestamp=datetime(2026, 8, 5),
        type=TransactionType.INCOME,
        category=Category.BUFFER,
        amount=15_000_000.0,
        source_or_merchant="Client Big Project",
    )
    await engine.process_income(tx_inc, month_year=month_year)

    # Add Expense Needs
    tx_exp1 = TransactionCreate(
        user_id=user_id,
        timestamp=datetime(2026, 8, 6),
        type=TransactionType.EXPENSE,
        category=Category.NEEDS,
        amount=4_000_000.0,
        source_or_merchant="Apartment & Groceries",
    )
    await engine.process_expense(tx_exp1, month_year=month_year)

    # Add Expense Wants
    tx_exp2 = TransactionCreate(
        user_id=user_id,
        timestamp=datetime(2026, 8, 7),
        type=TransactionType.EXPENSE,
        category=Category.WANTS,
        amount=1_200_000.0,
        source_or_merchant="Cafe & Cinema",
    )
    await engine.process_expense(tx_exp2, month_year=month_year)

    report_text, chart_bytes = await reporter.generate_report_for_user(user_id=user_id, month_year=month_year)

    assert "LAPORAN KEUANGAN FREELANCE" in report_text
    assert "15.000.000" in report_text
    assert "5.200.000" in report_text
    assert "BUFFER RUNWAY SAFETY" in report_text
    assert chart_bytes is not None
    assert len(chart_bytes) > 1000  # Valid PNG image bytes
