"""
Unit tests for the 3 New Advanced Features:
1. Smart Multi-Currency & Realtime Forex Converter (/kurs, /convert)
2. AI Tax Estimator & Rekap SPT Tahunan Form 1770 (/pajak, /export_spt)
3. Hourly Rate & Smart Project Pricing Calculator (/rate, /hitung_harga)
"""

import pytest
from datetime import datetime

from database.models import (
    UserSettings,
    MonthlySummary,
    PTKPStatus,
    TaxMethod,
)
from engine.currency_converter import currency_converter
from engine.tax_estimator import tax_estimator
from engine.pricing_calculator import pricing_calculator
from ai.nlp_parser import NLPParser
from tools.pdf_exporter import pdf_financial_exporter


@pytest.mark.asyncio
async def test_currency_converter_and_fees():
    # 1. Test live rates fetching
    rates = await currency_converter.fetch_live_rates()
    assert "USD" in rates
    assert rates["USD"] >= 15000.0
    assert "EUR" in rates
    assert "SGD" in rates

    # 2. Test direct USD to IDR conversion
    res_direct = await currency_converter.convert_to_idr(500.0, "USD", platform="direct")
    assert res_direct.from_currency == "USD"
    assert res_direct.original_amount == 500.0
    assert res_direct.converted_amount == 500.0 * res_direct.exchange_rate
    assert res_direct.estimated_platform_fee == 0.0
    assert res_direct.net_received_idr == res_direct.converted_amount

    # 3. Test Upwork 10% fee deduction
    res_upwork = await currency_converter.convert_to_idr(1000.0, "USD", platform="upwork")
    assert res_upwork.estimated_platform_fee == res_upwork.converted_amount * 0.10
    assert res_upwork.net_received_idr == res_upwork.converted_amount * 0.90
    assert "Upwork" in res_upwork.summary_text

    # 4. Test table rendering
    table_card = await currency_converter.render_rates_table()
    assert "KURS VALAS" in table_card
    assert "USD" in table_card


def test_currency_nlp_auto_conversion():
    # Test dollar symbol parsing
    amt1 = NLPParser._parse_amount_heuristic("Dapat fee Upwork $450")
    assert amt1 == 450.0 * 16250.0

    # Test currency code suffix
    amt2 = NLPParser._parse_amount_heuristic("Transfer klien Singapore 1200 SGD")
    assert amt2 == 1200.0 * 12250.0

    # Test euro symbol
    amt3 = NLPParser._parse_amount_heuristic("Beli software desain €50")
    assert amt3 == 50.0 * 17650.0

    # Test USDT crypto
    amt4 = NLPParser._parse_amount_heuristic("Terima fee payment 500 USDT")
    assert amt4 == 500.0 * 16300.0


def test_tax_estimator_nppn_and_progressive_brackets():
    settings = UserSettings(
        user_id=123,
        freelancer_name="Budi Taxpayer",
        target_salary=15_000_000.0,
        ptkp_status=PTKPStatus.TK0,  # 54jt
        nppn_rate=50.0,
    )

    # 12 months with 20jt income each = 240jt total gross
    summaries = [
        MonthlySummary(
            month_year=f"2026-{m:02d}",
            user_id=123,
            total_income=20_000_000.0,
            total_expense=5_000_000.0,
        )
        for m in range(1, 13)
    ]

    report = tax_estimator.calculate_annual_tax_report(
        year=2026,
        all_monthly_summaries=summaries,
        settings=settings,
        method=TaxMethod.NPPN_FREELANCE,
    )

    assert report.total_annual_gross == 240_000_000.0
    assert report.total_annual_net == 120_000_000.0       # 50% Norma
    assert report.ptkp_amount == 54_000_000.0             # TK/0
    assert report.pkp_amount == 66_000_000.0              # 120jt - 54jt

    # Brackets:
    # Lapisan 1 (5% up to 60jt) = 3.000.000
    # Lapisan 2 (15% on remaining 6jt) = 900.000
    # Total tax = 3.900.000
    assert report.total_tax_due == 3_900_000.0
    assert report.monthly_tax_installment == round(3_900_000.0 / 12.0, 2)
    assert len(report.brackets) == 2
    assert "SIMULASI & REKAP PAJAK" in report.summary_card


def test_tax_estimator_pph_final_umkm():
    settings = UserSettings(
        user_id=456,
        freelancer_name="Siti UMKM",
        ptkp_status=PTKPStatus.K1,  # 63jt
    )

    # 600jt annual revenue (above 500jt threshold)
    summaries = [
        MonthlySummary(
            month_year=f"2026-{m:02d}",
            user_id=456,
            total_income=50_000_000.0,
        )
        for m in range(1, 13)
    ]

    report = tax_estimator.calculate_annual_tax_report(
        year=2026,
        all_monthly_summaries=summaries,
        settings=settings,
        method=TaxMethod.PPH_FINAL_UMKM,
    )

    assert report.total_annual_gross == 600_000_000.0
    # Taxable slice above 500jt = 100jt * 0.5% = 500.000
    assert report.total_tax_due == 500_000.0


def test_pdf_spt_1770_generation():
    settings = UserSettings(
        user_id=789,
        freelancer_name="Ahmad Consultant",
        ptkp_status=PTKPStatus.TK0,
    )
    summaries = [
        MonthlySummary(
            month_year=f"2026-{m:02d}",
            user_id=789,
            total_income=15_000_000.0,
        )
        for m in range(1, 13)
    ]
    report = tax_estimator.calculate_annual_tax_report(
        year=2026,
        all_monthly_summaries=summaries,
        settings=settings,
    )

    pdf_bytes = pdf_financial_exporter.generate_spt_tax_report_pdf(report, settings)
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF")


def test_pricing_calculator_hourly_and_tiers():
    settings = UserSettings(
        user_id=999,
        target_salary=10_000_000.0,
        operational_budget=1_500_000.0,
        tax_percentage=10.0,
        weekly_billable_hours=30.0,  # 30 * 4.2 = 126 hrs/month
    )

    mar = pricing_calculator.calculate_minimum_hourly_rate(settings)
    assert mar > 0
    assert mar >= 100_000.0  # Around 115k - 120k / hour

    report = pricing_calculator.calculate_project_pricing(
        project_title="Redesign Web App",
        estimated_hours=30.0,
        settings=settings,
        complexity_level="Medium",
    )

    assert report is not None
    assert len(report.tiers) == 3
    assert report.tiers[0].tier_name.startswith("Floor Price")
    assert report.tiers[1].tier_name.startswith("Recommended")
    assert report.tiers[2].tier_name.startswith("Premium")

    # Verify price progression: Floor < Recommended < Premium
    assert report.tiers[0].total_price < report.tiers[1].total_price < report.tiers[2].total_price
    assert "KALKULATOR TARIF" in report.summary_card
