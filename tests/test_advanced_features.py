"""
Unit tests for new advanced and interactive features:
- Multi-Item Batch Parser
- Visual Dashboard Progress Bar
- 1-Click Undo / Transaction Reversal
- Smart Daily Safe-to-Spend Calculator
- Gemini Free Tier Engine & Voice Handlers
"""

import pytest
from datetime import datetime

from ai.nlp_parser import nlp_parser
from ai.gemini_engine import GeminiEngine
from engine.financial_engine import financial_engine, render_progress_bar
from database.sqlite_db import SQLiteBackend
from database.models import TransactionCreate, TransactionType, Category
from bot.keyboards import get_undo_keyboard, get_daily_checkin_keyboard


@pytest.mark.asyncio
async def test_multi_item_batch_parser():
    """Test parsing multi-item single messages with comma, newlines, and conjunctions."""
    # 1. Comma separated
    text1 = "beli buku 30rb, pensil 5rb, makan warteg 20k, bensin 25rb"
    items1 = await nlp_parser.parse_multi_text(text1)
    assert len(items1) == 4
    assert items1[0].amount == 30000.0
    assert items1[1].amount == 5000.0
    assert items1[2].amount == 20000.0
    assert items1[3].amount == 25000.0

    # 2. Conjunction separated
    text2 = "beli kopi 25rb dan bayar wifi 300rb"
    items2 = await nlp_parser.parse_multi_text(text2)
    assert len(items2) == 2
    assert items2[0].amount == 25000.0
    assert items2[1].amount == 300000.0
    assert items2[0].category == Category.WANTS
    assert items2[1].category == Category.OPERATIONAL

    # 3. Single item fallback
    text3 = "makan siang di warteg 20rb"
    items3 = await nlp_parser.parse_multi_text(text3)
    assert len(items3) == 1
    assert items3[0].amount == 20000.0
    assert items3[0].category == Category.NEEDS


def test_progress_bar_rendering():
    """Test ASCII visual progress bar rendering."""
    bar0 = render_progress_bar(0.0)
    assert "[░░░░░░░░░░]" in bar0
    assert "0.0%" in bar0

    bar50 = render_progress_bar(50.0)
    assert "[█████░░░░░]" in bar50
    assert "50.0%" in bar50

    bar100 = render_progress_bar(100.0)
    assert "[██████████]" in bar100
    assert "100.0%" in bar100


@pytest.mark.asyncio
async def test_daily_safe_spend_calculation(tmp_path):
    """Test smart daily safe-to-spend allowance calculation."""
    db_path = str(tmp_path / "test_safe.db")
    storage = SQLiteBackend(db_path=db_path)
    await storage.init_db()

    test_engine = financial_engine
    test_engine.storage = storage

    user_id = 99999
    # Add an expense
    await test_engine.process_expense(
        TransactionCreate(
            user_id=user_id,
            timestamp=datetime.now(),
            type=TransactionType.EXPENSE,
            category=Category.NEEDS,
            amount=500000.0,
            source_or_merchant="Superindo",
            notes="Belanja mingguan",
        )
    )

    safe_info = await test_engine.get_daily_safe_spend(user_id)
    assert safe_info["needs_spent"] == 500000.0
    assert safe_info["daily_safe_limit"] > 0
    assert safe_info["days_remaining"] >= 1
    assert safe_info["today_spent"] == 500000.0


@pytest.mark.asyncio
async def test_revert_undo_transaction(tmp_path):
    """Test 1-click transaction undo and balance reversal."""
    db_path = str(tmp_path / "test_undo.db")
    storage = SQLiteBackend(db_path=db_path)
    await storage.init_db()

    test_engine = financial_engine
    test_engine.storage = storage

    user_id = 88888
    # 1. Record expense
    tx_exp, _ = await test_engine.process_expense(
        TransactionCreate(
            user_id=user_id,
            timestamp=datetime.now(),
            type=TransactionType.EXPENSE,
            category=Category.NEEDS,
            amount=75000.0,
            source_or_merchant="Restoran",
            notes="Makan malam",
        )
    )

    m_y = datetime.now().strftime("%Y-%m")
    sum_before = await storage.get_monthly_summary(m_y, user_id)
    assert sum_before.total_expense == 75000.0

    # 2. Undo expense
    success, msg, undone_tx = await test_engine.revert_transaction(tx_exp.id, user_id)
    assert success is True
    assert undone_tx is not None
    assert undone_tx.id == tx_exp.id

    sum_after = await storage.get_monthly_summary(m_y, user_id)
    assert sum_after.total_expense == 0.0

    # 3. Verify deleted from transactions list
    txs = await storage.get_transactions(user_id)
    assert len(txs) == 0


def test_keyboards():
    """Verify undo and daily checkin keyboard structures."""
    undo_kb = get_undo_keyboard("test_id_123")
    assert undo_kb.inline_keyboard[0][0].callback_data == "tx_undo:test_id_123"

    checkin_kb = get_daily_checkin_keyboard()
    assert len(checkin_kb.inline_keyboard) == 2
    assert checkin_kb.inline_keyboard[0][1].callback_data == "checkin:zero"


def test_gemini_engine_fallback():
    """Verify Gemini engine handles empty API keys gracefully."""
    engine = GeminiEngine(api_key="")
    assert engine.is_available is False
