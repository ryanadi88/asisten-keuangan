"""
Automated Monthly Reporting Module for Freelance AI Financial Engine.
Generates comprehensive Markdown summaries and visual charts.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from config import settings, format_currency, get_current_month_year
from database.base import StorageBackend
from database import get_storage
from database.models import Transaction, TransactionType, Category, MonthlySummary, UserSettings
from engine.financial_engine import FreelanceFinancialEngine, financial_engine
from reporter.chart_generator import chart_generator, make_ascii_bar

logger = logging.getLogger(__name__)


class MonthlyReporter:
    def __init__(self, storage: Optional[StorageBackend] = None, engine: Optional[FreelanceFinancialEngine] = None):
        self.storage = storage or get_storage()
        self.engine = engine or financial_engine

    async def generate_report_for_user(
        self,
        user_id: int,
        month_year: Optional[str] = None,
    ) -> Tuple[str, Optional[bytes]]:
        """
        Generate full monthly report text and chart image buffer.
        """
        m_y = month_year or get_current_month_year()
        summary = await self.storage.get_monthly_summary(m_y, user_id)
        user_settings = await self.storage.get_user_settings(user_id)
        transactions = await self.storage.get_transactions(user_id=user_id, month_year=m_y, limit=500)
        currency = user_settings.currency

        # 1. Compute Category Totals
        category_spent: Dict[str, float] = {
            Category.NEEDS.value: 0.0,
            Category.WANTS.value: 0.0,
            Category.OPERATIONAL.value: 0.0,
            Category.INVESTMENT.value: 0.0,
            Category.EMERGENCY.value: 0.0,
        }
        for tx in transactions:
            if tx.type == TransactionType.EXPENSE:
                cat_val = tx.category.value
                category_spent[cat_val] = category_spent.get(cat_val, 0.0) + tx.amount

        # 2. Category Budgets & ASCII Bars
        needs_limit = user_settings.needs_budget
        needs_spent = category_spent[Category.NEEDS.value]
        needs_pct = (needs_spent / needs_limit * 100) if needs_limit > 0 else 0.0

        wants_limit = user_settings.wants_budget
        wants_spent = category_spent[Category.WANTS.value]
        wants_pct = (wants_spent / wants_limit * 100) if wants_limit > 0 else 0.0

        ops_limit = user_settings.operational_budget
        ops_spent = category_spent[Category.OPERATIONAL.value]
        ops_pct = (ops_spent / ops_limit * 100) if ops_limit > 0 else 0.0

        # 3. Health & Runway Calculation
        health_info = await self.engine.get_financial_health(user_id, m_y)
        runway = summary.buffer_runway_months
        salary_pct = (
            (summary.actual_salary_drawn / summary.target_salary * 100)
            if summary.target_salary > 0
            else 100.0
        )

        net_cashflow = summary.total_income - summary.total_expense

        # 4. Compose Formatted Markdown Report
        report_md = (
            f"📊 *LAPORAN KEUANGAN FREELANCE — {m_y}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💵 *CASH FLOW OVERVIEW*\n"
            f"• Gross Total Income: `{format_currency(summary.total_income, currency)}`\n"
            f"• Total Expenses: `{format_currency(summary.total_expense, currency)}`\n"
            f"• Net Cashflow: `{'🟢 +' if net_cashflow >= 0 else '🔴 -'}{format_currency(abs(net_cashflow), currency)}`\n\n"
            f"🎯 *ALOKASI & SMOOTHING INCOME*\n"
            f"• Target Gaji Minimum: `{format_currency(summary.target_salary, currency)}`\n"
            f"• Gaji Ditarik Bulan Ini: `{format_currency(summary.actual_salary_drawn, currency)}` ({salary_pct:.0f}%)\n"
            f"• Cadangan Pajak & Ops (10%): `{format_currency(summary.tax_reserve, currency)}`\n"
            f"• Saldo Buffer Smoothing Pool: `{format_currency(summary.buffer_fund_balance, currency)}`\n"
            f"• Dana Darurat: `{format_currency(summary.emergency_fund, currency)}`\n"
            f"• Portofolio Investasi: `{format_currency(summary.investment_total, currency)}`\n\n"
            f"🛡️ *BUFFER RUNWAY SAFETY*\n"
            f"• Ketahanan Dana: *{runway} Bulan Biaya Hidup*\n"
            f"• Status: *{health_info['health_badge']}*\n\n"
            f"📋 *PENGELUARAN PER KATEGORI*\n"
            f"• 🏠 *Needs:* `{format_currency(needs_spent, currency)}` / `{format_currency(needs_limit, currency)}`\n"
            f"  {make_ascii_bar(needs_pct)}\n"
            f"• ☕ *Wants:* `{format_currency(wants_spent, currency)}` / `{format_currency(wants_limit, currency)}`\n"
            f"  {make_ascii_bar(wants_pct)}\n"
            f"• 💻 *Operational:* `{format_currency(ops_spent, currency)}` / `{format_currency(ops_limit, currency)}`\n"
            f"  {make_ascii_bar(ops_pct)}\n"
            f"• 📈 *Investasi Baru:* `{format_currency(category_spent[Category.INVESTMENT.value], currency)}`\n\n"
            f"💡 *SARAN ARSITEK KEUANGAN:*\n"
            f"_{health_info['health_advice']}_\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        # 5. Generate Visual Chart Image
        chart_bytes = chart_generator.generate_monthly_chart(
            summary=summary,
            transactions=transactions,
            currency=currency,
        )

        return report_md, chart_bytes


monthly_reporter = MonthlyReporter()
