"""
Unit tests for Financial Health scoring, Runway classification, and Currency Formatting.
"""

import pytest
from datetime import datetime

from config import format_currency, get_current_month_year
from database.models import Category, MonthlySummary, UserSettings
from database.sqlite_db import SQLiteBackend
from engine.financial_engine import FreelanceFinancialEngine


def test_currency_formatting():
    assert format_currency(10_000_000, "IDR") == "Rp10.000.000"
    assert format_currency(50_000, "RP") == "Rp50.000"
    assert format_currency(1200.50, "USD") == "$1,200.50"
    assert format_currency(100, "$") == "$100.00"
    assert format_currency(75.5, "EUR") == "€75.50"
    assert format_currency(50, "GBP") == "£50.00"
    assert format_currency(200, "SGD") == "S$200.00"


@pytest.mark.asyncio
async def test_financial_health_ratings(tmp_path):
    db_path = str(tmp_path / "test_health.db")
    storage = SQLiteBackend(db_path=db_path)
    await storage.init_db()
    engine = FreelanceFinancialEngine(storage=storage)

    user_id = 500
    m_y = "2026-08"

    # Case 1: Low runway (< 3 months) -> Vulnerable
    summary = await engine.get_or_create_monthly_summary(user_id, m_y)
    summary.target_salary = 10_000_000.0
    summary.buffer_fund_balance = 10_000_000.0  # 1 month
    await storage.save_monthly_summary(summary)

    health = await engine.get_financial_health(user_id, m_y)
    assert health["runway_months"] == 1.0
    assert "Vulnerable" in health["health_badge"] or "BUTUH PERKUATAN" in health["health_badge"]

    # Case 2: Moderate runway (3-6 months) -> Stable
    summary.buffer_fund_balance = 40_000_000.0  # 4 months
    await storage.save_monthly_summary(summary)
    health = await engine.get_financial_health(user_id, m_y)
    assert health["runway_months"] == 4.0
    assert "STABIL" in health["health_badge"]

    # Case 3: High runway (>= 6 months) -> Very Healthy
    summary.buffer_fund_balance = 70_000_000.0  # 7 months
    await storage.save_monthly_summary(summary)
    health = await engine.get_financial_health(user_id, m_y)
    assert health["runway_months"] == 7.0
    assert "SANGAT SEHAT" in health["health_badge"]
