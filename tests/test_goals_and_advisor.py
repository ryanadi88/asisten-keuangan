"""
Unit tests for Goals Auto-Split, Subscriptions, AI Financial Advisor, and Health Score.
"""

import pytest
from datetime import datetime

from engine.financial_engine import FreelanceFinancialEngine
from database.sqlite_db import SQLiteBackend
from database.models import (
    TransactionCreate,
    TransactionType,
    Category,
    FinancialGoalCreate,
    SubscriptionCreate,
)
from ai.gemini_engine import GeminiEngine
from bot.keyboards import get_goals_keyboard, get_subscriptions_keyboard


@pytest.mark.asyncio
async def test_goal_auto_split_on_income(tmp_path):
    """Test auto-allocating percentage of incoming freelance fee into active wishlist goals."""
    db_path = str(tmp_path / "test_goals.db")
    storage = SQLiteBackend(db_path=db_path)
    await storage.init_db()

    engine = FreelanceFinancialEngine(storage=storage)
    user_id = 12345

    # 1. Create a goal: Macbook M3, target 20jt, 10% allocation
    goal = await storage.add_goal(
        FinancialGoalCreate(
            user_id=user_id,
            name="Macbook M3",
            target_amount=20_000_000.0,
            current_amount=0.0,
            allocation_percent=10.0,
            is_completed=False,
        )
    )
    assert goal.id is not None
    assert goal.percentage_achieved == 0.0

    # 2. Process incoming income of 5,000,000 IDR
    tx_create = TransactionCreate(
        user_id=user_id,
        timestamp=datetime.now(),
        type=TransactionType.INCOME,
        category=Category.NEEDS,
        amount=5_000_000.0,
        source_or_merchant="Client Project A",
        notes="Down Payment",
    )
    tx, split_result = await engine.process_income(tx_create)

    # 10% of 5,000,000 = 500,000 should be auto-allocated to goal
    updated_goal = await storage.get_goal_by_id(goal.id, user_id)
    assert updated_goal is not None
    assert updated_goal.current_amount == 500_000.0
    assert updated_goal.percentage_achieved == 2.5
    assert updated_goal.is_completed is False
    assert "AUTO-SPLIT TARGET & WISHLIST" in split_result.message
    assert "Macbook M3" in split_result.message


@pytest.mark.asyncio
async def test_goal_completion(tmp_path):
    """Test that a goal is marked completed when target amount is reached."""
    db_path = str(tmp_path / "test_goal_comp.db")
    storage = SQLiteBackend(db_path=db_path)
    await storage.init_db()

    engine = FreelanceFinancialEngine(storage=storage)
    user_id = 12345

    # Target 1jt, 20% allocation
    goal = await storage.add_goal(
        FinancialGoalCreate(
            user_id=user_id,
            name="Mechanical Keyboard",
            target_amount=1_000_000.0,
            current_amount=800_000.0,
            allocation_percent=20.0,
            is_completed=False,
        )
    )

    # Receive 2jt income -> 20% is 400k, but only 200k needed to finish goal
    tx_create = TransactionCreate(
        user_id=user_id,
        timestamp=datetime.now(),
        type=TransactionType.INCOME,
        category=Category.NEEDS,
        amount=2_000_000.0,
        source_or_merchant="Client B",
    )
    await engine.process_income(tx_create)

    updated_goal = await storage.get_goal_by_id(goal.id, user_id)
    assert updated_goal.current_amount == 1_000_000.0
    assert updated_goal.is_completed is True
    assert updated_goal.percentage_achieved == 100.0


def test_goal_eta_calculation():
    """Test goal ETA estimation based on average monthly income."""
    engine = FreelanceFinancialEngine()
    from database.models import FinancialGoal

    goal = FinancialGoal(
        id="test1",
        user_id=1,
        name="Kamera Sony",
        target_amount=12_000_000.0,
        current_amount=2_000_000.0,  # Remaining 10,000,000
        allocation_percent=10.0,      # 10% of 10jt = 1jt/month
        is_completed=False,
    )

    eta = engine.calculate_goal_eta(goal, avg_monthly_income=10_000_000.0)
    assert "10 Bulan lagi" in eta


@pytest.mark.asyncio
async def test_subscriptions_crud(tmp_path):
    """Test recurring subscriptions adding, listing, toggling, and deletion."""
    db_path = str(tmp_path / "test_subs.db")
    storage = SQLiteBackend(db_path=db_path)
    await storage.init_db()

    user_id = 54321
    sub1 = await storage.add_subscription(
        SubscriptionCreate(
            user_id=user_id,
            name="ChatGPT Plus",
            amount=330_000.0,
            billing_cycle="monthly",
            billing_day=15,
            category=Category.OPERATIONAL,
            is_active=True,
        )
    )
    sub2 = await storage.add_subscription(
        SubscriptionCreate(
            user_id=user_id,
            name="Spotify Premium",
            amount=55_000.0,
            billing_cycle="monthly",
            billing_day=28,
            category=Category.WANTS,
            is_active=True,
        )
    )

    subs = await storage.get_subscriptions(user_id)
    assert len(subs) == 2

    # Toggle active
    sub1.is_active = False
    await storage.update_subscription(sub1)

    active_subs = await storage.get_subscriptions(user_id, is_active=True)
    assert len(active_subs) == 1
    assert active_subs[0].name == "Spotify Premium"

    # Delete
    deleted = await storage.delete_subscription(sub2.id, user_id)
    assert deleted is True
    assert len(await storage.get_subscriptions(user_id)) == 1


@pytest.mark.asyncio
async def test_financial_health_score(tmp_path):
    """Test financial health score computation and grading."""
    db_path = str(tmp_path / "test_health.db")
    storage = SQLiteBackend(db_path=db_path)
    await storage.init_db()

    engine = FreelanceFinancialEngine(storage=storage)
    user_id = 77777

    # Compute base health report
    report = await engine.calculate_financial_health_score(user_id)
    assert 0 <= report.score <= 100
    assert report.grade in ["A+", "A", "B", "C", "D"]
    assert len(report.recommendations) > 0
    assert "SKOR KESEHATAN KEUANGAN" in report.summary_text


def test_keyboards_goals_and_subs():
    """Verify goals and subscriptions keyboard generation."""
    from database.models import FinancialGoal, Subscription

    goals = [
        FinancialGoal(
            id="g1",
            user_id=1,
            name="Macbook",
            target_amount=20000000.0,
            current_amount=5000000.0,
            allocation_percent=10.0,
            is_completed=False,
        )
    ]
    g_kb = get_goals_keyboard(goals)
    assert len(g_kb.inline_keyboard) == 2
    assert "goal_view:g1" in g_kb.inline_keyboard[0][0].callback_data

    subs = [
        Subscription(
            id="s1",
            user_id=1,
            name="ChatGPT",
            amount=300000.0,
            billing_cycle="monthly",
            billing_day=15,
            category=Category.OPERATIONAL,
            is_active=True,
        )
    ]
    s_kb = get_subscriptions_keyboard(subs)
    assert len(s_kb.inline_keyboard) == 2
    assert "sub_view:s1" in s_kb.inline_keyboard[0][0].callback_data
