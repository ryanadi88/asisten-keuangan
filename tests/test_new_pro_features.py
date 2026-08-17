"""
Unit tests for the 4 Advanced Freelance Financial Features:
1. Quotation & SPH Generator (/quote)
2. Termin & Milestone Tracker (/termin)
3. Instant Affordability Radar (/beli)
4. 90-Day Cashflow Forecaster (/forecast)
"""

import os
import pytest
from datetime import datetime

from database.sqlite_db import SQLiteBackend
from database.models import (
    QuotationCreate,
    QuotationStatus,
    ProjectTerminCreate,
    MilestoneStatus,
    MonthlySummary,
    UserSettings,
    Invoice,
    InvoiceStatus,
    Subscription,
    Category,
    FinancialGoal,
    AffordabilityRating,
)
from quotation.quotation_parser import quotation_parser
from quotation.quotation_generator import quotation_generator
from termin.termin_tracker import termin_tracker
from engine.affordability_radar import affordability_radar
from engine.cashflow_forecaster import cashflow_forecaster


@pytest.mark.asyncio
async def test_quotation_parser_and_storage(tmp_path):
    db_path = str(tmp_path / "test_pro.db")
    storage = SQLiteBackend(db_path=db_path)
    await storage.init_db()

    user_id = 999
    raw_cmd = "/quote PT Maju Jaya | Redesign Website E-Commerce | 15jt | 14 Hari Kerja | DP 50%"
    parsed = quotation_parser.parse_command_text(raw_cmd, user_id)

    assert parsed is not None
    assert parsed.client_name == "PT Maju Jaya"
    assert parsed.project_title == "Redesign Website E-Commerce"
    assert parsed.amount == 15_000_000.0
    assert parsed.timeline == "14 Hari Kerja"
    assert parsed.dp_terms == "DP 50%"

    created_q = await storage.add_quotation(parsed)
    assert created_q.id.startswith("SPH-")

    # Generate PDF
    settings = UserSettings(user_id=user_id, freelancer_name="Agus Freelancer")
    pdf_bytes = quotation_generator.generate_pdf(created_q, settings)
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF")

    # Fetch from storage
    quotes = await storage.get_quotations(user_id=user_id)
    assert len(quotes) == 1
    assert quotes[0].id == created_q.id

    # Update status
    await storage.update_quotation_status(created_q.id, user_id, QuotationStatus.ACCEPTED, "INV-1234")
    updated_q = await storage.get_quotation_by_id(created_q.id, user_id)
    assert updated_q.status == QuotationStatus.ACCEPTED
    assert updated_q.converted_invoice_id == "INV-1234"


@pytest.mark.asyncio
async def test_termin_project_and_milestone_invoice(tmp_path):
    db_path = str(tmp_path / "test_termin.db")
    storage = SQLiteBackend(db_path=db_path)
    await storage.init_db()

    user_id = 888
    raw_cmd = "/termin PT Bintang Terang | Mobile App Flutter | 20jt | 50% 30% 20%"
    parsed = termin_tracker.parse_termin_command(raw_cmd, user_id)

    assert parsed is not None
    assert parsed.client_name == "PT Bintang Terang"
    assert parsed.total_amount == 20_000_000.0
    assert len(parsed.milestones) == 3
    assert parsed.milestones[0].amount == 10_000_000.0  # 50%
    assert parsed.milestones[1].amount == 6_000_000.0   # 30%
    assert parsed.milestones[2].amount == 4_000_000.0   # 20%

    created_t = await storage.add_termin(parsed)
    assert created_t.id.startswith("PRJ-")
    assert created_t.total_unbilled == 20_000_000.0

    # Invoice milestone 1 (DP 50%)
    inv, msg = await termin_tracker.create_invoice_for_milestone(created_t, "m1", storage)
    assert inv is not None
    assert inv.amount == 10_000_000.0
    assert inv.status == InvoiceStatus.UNPAID

    # Verify updated termin in DB
    refreshed_t = await storage.get_termin_by_id(created_t.id, user_id)
    assert refreshed_t.milestones[0].status == MilestoneStatus.INVOICED
    assert refreshed_t.milestones[0].invoice_id == inv.id
    assert refreshed_t.total_billed == 10_000_000.0
    assert refreshed_t.total_unbilled == 10_000_000.0

    # Render card
    card = termin_tracker.render_termin_card(refreshed_t)
    assert "PROYEK TERMIN" in card
    assert "PT Bintang Terang" in card


def test_affordability_radar_green_yellow_red():
    summary = MonthlySummary(
        month_year="2026-08",
        user_id=101,
        total_income=20_000_000.0,
        total_expense=3_000_000.0,
        target_salary=10_000_000.0,
        actual_salary_drawn=10_000_000.0,
        buffer_fund_balance=25_000_000.0,
        emergency_fund=10_000_000.0,
        investment_total=5_000_000.0,
        tax_reserve=2_000_000.0,
    )
    settings = UserSettings(
        user_id=101,
        needs_budget=5_000_000.0,
        wants_budget=3_000_000.0,
    )

    # 1. GREEN Case: Small purchase well within Wants budget
    rep_green = affordability_radar.evaluate_purchase(
        item_name="Kopi & Buku",
        price=150_000.0,
        summary=summary,
        settings=settings,
        wants_spent=500_000.0,
    )
    assert rep_green.rating == AffordabilityRating.GREEN
    assert "SANGAT AMAN" in rep_green.verdict_badge

    # 2. YELLOW Case: Exceeds wants budget but safe buffer runway
    rep_yellow = affordability_radar.evaluate_purchase(
        item_name="Sepatu Olahraga",
        price=4_000_000.0,
        summary=summary,
        settings=settings,
        wants_spent=1_000_000.0,
    )
    assert rep_yellow.rating == AffordabilityRating.YELLOW
    assert "PERTIMBANGKAN" in rep_yellow.verdict_badge

    # 3. RED Case: Crushes buffer runway
    poor_summary = MonthlySummary(
        month_year="2026-08",
        user_id=101,
        total_income=5_000_000.0,
        total_expense=4_000_000.0,
        target_salary=10_000_000.0,
        actual_salary_drawn=5_000_000.0,
        buffer_fund_balance=3_000_000.0,
        emergency_fund=0.0,
        investment_total=0.0,
        tax_reserve=0.0,
    )
    rep_red = affordability_radar.evaluate_purchase(
        item_name="Motor Baru",
        price=18_000_000.0,
        summary=poor_summary,
        settings=settings,
        wants_spent=2_500_000.0,
    )
    assert rep_red.rating == AffordabilityRating.RED
    assert "TUNDA DULU" in rep_red.verdict_badge


def test_cmd_affordability_command_parsing():
    from ai.nlp_parser import NLPParser
    # Test "/beli ps5 5jt"
    clean = "ps5 5jt"
    parts = clean.split()
    assert len(parts) >= 2
    price = NLPParser._parse_indonesian_number(parts[-1])
    item_name = " ".join(parts[:-1])
    assert price == 5_000_000.0
    assert item_name == "ps5"

    # Test multi-word item "/beli sepatu lari marathon 1.5jt"
    clean2 = "sepatu lari marathon 1.5jt"
    parts2 = clean2.split()
    price2 = NLPParser._parse_indonesian_number(parts2[-1])
    item_name2 = " ".join(parts2[:-1])
    assert price2 == 1_500_000.0
    assert item_name2 == "sepatu lari marathon"


def test_cashflow_forecaster_90_days():
    summary = MonthlySummary(
        month_year="2026-08",
        user_id=202,
        total_income=15_000_000.0,
        total_expense=6_000_000.0,
        target_salary=10_000_000.0,
        actual_salary_drawn=10_000_000.0,
        buffer_fund_balance=20_000_000.0,
        emergency_fund=5_000_000.0,
        investment_total=0.0,
        tax_reserve=1_500_000.0,
    )
    settings = UserSettings(
        user_id=202,
        target_salary=10_000_000.0,
        needs_budget=5_000_000.0,
        wants_budget=2_000_000.0,
    )
    subs = [
        Subscription(
            id="sub1",
            user_id=202,
            name="ChatGPT",
            amount=300_000.0,
            billing_day=15,
            category=Category.OPERATIONAL,
            is_active=True,
        )
    ]
    unpaid_invs = [
        Invoice(
            id="INV-99",
            user_id=202,
            client_name="PT Delta",
            project_title="Consulting",
            amount=12_000_000.0,
            currency="IDR",
            issue_date="2026-08-10",
            due_date="2026-09-15",
            status=InvoiceStatus.UNPAID,
        )
    ]

    report = cashflow_forecaster.forecast_90_days(
        summary=summary,
        settings=settings,
        unpaid_invoices=unpaid_invs,
        active_subscriptions=subs,
    )

    assert report is not None
    assert len(report.months) == 3
    assert report.current_buffer_balance == 20_000_000.0
    assert report.optimistic_end_balance > 0
    assert len(report.strategic_insights) > 0
    assert "SIMULASI ARUS KAS 90 HARI" in report.summary_card
