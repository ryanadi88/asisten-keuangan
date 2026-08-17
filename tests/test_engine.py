"""
Unit tests for Freelance Financial Engine logic (Dynamic Income Splitter & Smart Budget Guard).
"""

import pytest
from datetime import datetime

from database.sqlite_db import SQLiteBackend
from database.models import (
    TransactionCreate,
    TransactionType,
    Category,
    BudgetGuardStatus,
)
from engine.financial_engine import FreelanceFinancialEngine


async def create_engine_for_test(tmp_path, name: str) -> FreelanceFinancialEngine:
    db_path = str(tmp_path / f"{name}.db")
    storage = SQLiteBackend(db_path=db_path)
    await storage.init_db()
    return FreelanceFinancialEngine(storage=storage)


@pytest.mark.asyncio
async def test_income_splitter_basic(tmp_path):
    """
    Test single income trigger:
    Target Salary = 10,000,000
    Tax Rate = 10%
    Gross Income = 8,000,000
    - Tax Reserve (10%): 800,000
    - Net Income: 7,200,000
    - Salary Drawn Allocated: 7,200,000 (quota left: 10,000,000)
    - Buffer Surplus: 0
    - Salary target met: False
    """
    test_engine = await create_engine_for_test(tmp_path, "income_basic")
    user_id = 101
    month_year = "2026-08"

    tx_create = TransactionCreate(
        user_id=user_id,
        timestamp=datetime(2026, 8, 10, 12, 0),
        type=TransactionType.INCOME,
        category=Category.BUFFER,
        amount=8_000_000.0,
        source_or_merchant="Client A",
        notes="Project milestone 1",
    )

    persisted_tx, split_result = await test_engine.process_income(tx_create, month_year=month_year)

    assert split_result.gross_income == 8_000_000.0
    assert split_result.tax_reserve_amount == 800_000.0
    assert split_result.net_income == 7_200_000.0
    assert split_result.salary_drawn_allocated == 7_200_000.0
    assert split_result.total_salary_drawn_month == 7_200_000.0
    assert split_result.buffer_pool_allocated == 0.0
    assert split_result.salary_target_met is False


@pytest.mark.asyncio
async def test_income_splitter_surplus_to_buffer(tmp_path):
    """
    Test consecutive incomes triggering surplus into buffer fund:
    1st Income: Gross 10,000,000 -> Tax: 1,000,000 -> Net: 9,000,000 -> Salary: 9,000,000 (Target: 10M)
    2nd Income: Gross 10,000,000 -> Tax: 1,000,000 -> Net: 9,000,000 -> Salary: 1,000,000 (Target Reached) -> Buffer: 8,000,000
    """
    test_engine = await create_engine_for_test(tmp_path, "income_surplus")
    user_id = 102
    month_year = "2026-08"

    # 1st Income
    tx1 = TransactionCreate(
        user_id=user_id,
        timestamp=datetime(2026, 8, 5),
        type=TransactionType.INCOME,
        category=Category.BUFFER,
        amount=10_000_000.0,
        source_or_merchant="Client A",
    )
    await test_engine.process_income(tx1, month_year=month_year)

    # 2nd Income
    tx2 = TransactionCreate(
        user_id=user_id,
        timestamp=datetime(2026, 8, 18),
        type=TransactionType.INCOME,
        category=Category.BUFFER,
        amount=10_000_000.0,
        source_or_merchant="Client B",
    )
    _, split2 = await test_engine.process_income(tx2, month_year=month_year)

    assert split2.tax_reserve_amount == 1_000_000.0
    assert split2.salary_drawn_allocated == 1_000_000.0
    assert split2.total_salary_drawn_month == 10_000_000.0
    assert split2.salary_target_met is True
    assert split2.buffer_pool_allocated == 8_000_000.0
    assert split2.current_buffer_balance == 8_000_000.0
    assert split2.buffer_runway_months == 0.8  # 8M / 10M


@pytest.mark.asyncio
async def test_smart_budget_guard_thresholds(tmp_path):
    """
    Test Smart Budget Guard:
    Default Needs Budget = 5,000,000
    - Expense 1: 3,500,000 (70%) -> Status: OK
    - Expense 2: 700,000 (Total 4,200,000 = 84%) -> Status: WARNING (>=80%)
    - Expense 3: 1,000,000 (Total 5,200,000 = 104%) -> Status: BREACH (>=100%)
    """
    test_engine = await create_engine_for_test(tmp_path, "guard_thresholds")
    user_id = 103
    month_year = "2026-08"

    # Step 1: 70% Spend
    tx1 = TransactionCreate(
        user_id=user_id,
        timestamp=datetime(2026, 8, 2),
        type=TransactionType.EXPENSE,
        category=Category.NEEDS,
        amount=3_500_000.0,
        source_or_merchant="Groceries & Rent",
    )
    _, guard1 = await test_engine.process_expense(tx1, month_year=month_year)
    assert guard1.status == BudgetGuardStatus.OK
    assert guard1.percentage_used == 70.0

    # Step 2: 84% Spend (Warning)
    tx2 = TransactionCreate(
        user_id=user_id,
        timestamp=datetime(2026, 8, 10),
        type=TransactionType.EXPENSE,
        category=Category.NEEDS,
        amount=700_000.0,
        source_or_merchant="Utilities & Wifi",
    )
    _, guard2 = await test_engine.process_expense(tx2, month_year=month_year)
    assert guard2.status == BudgetGuardStatus.WARNING
    assert guard2.percentage_used == 84.0
    assert "WARNING" in guard2.message

    # Step 3: 104% Spend (Breach)
    tx3 = TransactionCreate(
        user_id=user_id,
        timestamp=datetime(2026, 8, 20),
        type=TransactionType.EXPENSE,
        category=Category.NEEDS,
        amount=1_000_000.0,
        source_or_merchant="Medical & Extra Needs",
    )
    _, guard3 = await test_engine.process_expense(tx3, month_year=month_year)
    assert guard3.status == BudgetGuardStatus.BREACH
    assert guard3.percentage_used == 104.0
    assert "BREACH" in guard3.message


@pytest.mark.asyncio
async def test_draw_salary_from_buffer(tmp_path):
    """
    Test drawing base salary from buffer fund during dry freelance months.
    """
    test_engine = await create_engine_for_test(tmp_path, "draw_buffer")
    user_id = 104
    month_year = "2026-08"

    # Seed buffer fund with 15,000,000
    summary = await test_engine.get_or_create_monthly_summary(user_id, month_year)
    summary.buffer_fund_balance = 15_000_000.0
    summary.actual_salary_drawn = 0.0
    await test_engine.storage.save_monthly_summary(summary)

    # Draw 10,000,000 (target salary)
    success, msg = await test_engine.draw_salary_from_buffer(user_id, amount=10_000_000.0, month_year=month_year)
    assert success is True
    assert "Berhasil menarik" in msg

    # Verify updated summary
    updated = await test_engine.get_or_create_monthly_summary(user_id, month_year)
    assert updated.actual_salary_drawn == 10_000_000.0
    assert updated.buffer_fund_balance == 5_000_000.0
