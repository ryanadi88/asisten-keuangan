"""
Unit tests for SQLite database backend.
"""

import pytest
import os
from datetime import datetime

from database.sqlite_db import SQLiteBackend
from database.models import (
    TransactionCreate,
    TransactionType,
    Category,
    MonthlySummary,
    UserSettings,
)


@pytest.fixture
def temp_db_path(tmp_path):
    return str(tmp_path / "test_finance.db")


@pytest.mark.asyncio
async def test_sqlite_crud(temp_db_path):
    backend = SQLiteBackend(db_path=temp_db_path)
    await backend.init_db()

    # 1. Test User Settings
    user_id = 999
    settings = await backend.get_user_settings(user_id)
    assert settings.user_id == user_id
    assert settings.target_salary == 10_000_000.0

    settings.target_salary = 12_000_000.0
    await backend.update_user_settings(settings)
    updated_settings = await backend.get_user_settings(user_id)
    assert updated_settings.target_salary == 12_000_000.0

    # 2. Test Add Transaction
    tx_create = TransactionCreate(
        user_id=user_id,
        timestamp=datetime(2026, 8, 15, 10, 30),
        type=TransactionType.INCOME,
        category=Category.BUFFER,
        amount=5_000_000.0,
        source_or_merchant="Client Acme Corp",
        notes="Landing page milestone 1",
    )
    tx = await backend.add_transaction(tx_create)
    assert tx.id is not None
    assert tx.amount == 5_000_000.0
    assert tx.source_or_merchant == "Client Acme Corp"

    # 3. Test Get Transactions
    tx_list = await backend.get_transactions(user_id=user_id, month_year="2026-08")
    assert len(tx_list) == 1
    assert tx_list[0].id == tx.id

    # 4. Test Monthly Summary
    summary = await backend.get_monthly_summary("2026-08", user_id)
    assert summary.month_year == "2026-08"
    assert summary.total_income == 0.0

    summary.total_income = 5_000_000.0
    summary.buffer_fund_balance = 1_500_000.0
    await backend.save_monthly_summary(summary)

    saved_summary = await backend.get_monthly_summary("2026-08", user_id)
    assert saved_summary.total_income == 5_000_000.0
    assert saved_summary.buffer_fund_balance == 1_500_000.0

    # 5. Test Delete Transaction
    deleted = await backend.delete_transaction(tx.id, user_id)
    assert deleted is True
    assert len(await backend.get_transactions(user_id=user_id)) == 0
