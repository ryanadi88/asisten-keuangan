"""
90-Day Cashflow Forecasting Engine for Freelancers.
Simulates forward-looking cashflow for the next 3 months based on invoices, termins, living burn, and subscriptions.
"""

import calendar
import logging
from typing import Optional, List
from datetime import datetime, timedelta

from config import format_currency
from database.models import (
    MonthlySummary,
    UserSettings,
    Invoice,
    InvoiceStatus,
    Subscription,
    ProjectTermin,
    CashflowMonthForecast,
    CashflowForecastReport,
)

logger = logging.getLogger(__name__)


class CashflowForecaster:
    """Simulates 90-day forward cashflow and runway for freelancers."""

    @staticmethod
    def forecast_90_days(
        summary: MonthlySummary,
        settings: UserSettings,
        unpaid_invoices: List[Invoice],
        active_subscriptions: List[Subscription],
        active_termins: Optional[List[ProjectTermin]] = None,
        avg_monthly_income: Optional[float] = None,
    ) -> CashflowForecastReport:
        """Run 3-month cashflow simulation."""
        currency = settings.currency
        current_buffer = summary.buffer_fund_balance
        subs_burn = sum(s.amount for s in active_subscriptions if s.is_active)
        fixed_burn = settings.needs_budget + subs_burn
        if fixed_burn <= 0:
            fixed_burn = 5_000_000.0

        estimated_living_spend = fixed_burn + (settings.wants_budget * 0.7)  # Expected burn
        baseline_income = avg_monthly_income if (avg_monthly_income and avg_monthly_income > 0) else settings.target_salary

        # Build 3 upcoming months
        today = datetime.now()
        months_forecast: List[CashflowMonthForecast] = []
        running_balance = current_buffer
        indo_months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

        for i in range(1, 4):
            # Calculate target month year
            target_month = (today.month + i - 1) % 12 + 1
            target_year = today.year + ((today.month + i - 1) // 12)
            m_y_str = f"{target_year:04d}-{target_month:02d}"
            m_name = f"{indo_months[target_month - 1]} {target_year}"

            # Calculate confirmed invoices due in target month
            confirmed_inv_amount = sum(
                inv.amount for inv in unpaid_invoices
                if inv.due_date and inv.due_date.startswith(m_y_str) and inv.status in [InvoiceStatus.UNPAID, InvoiceStatus.OVERDUE]
            )

            # Calculate pending termin milestones
            termin_amount = 0.0
            if active_termins:
                for t in active_termins:
                    if not t.is_completed:
                        for m in t.milestones:
                            if m.due_date and m.due_date.startswith(m_y_str) and m.status.value != "PAID":
                                termin_amount += m.amount

            # Projected Income = Max(confirmed receivables, baseline recurring expected)
            total_proj_income = max(baseline_income, confirmed_inv_amount + termin_amount)
            net_cash = total_proj_income - estimated_living_spend
            running_balance += net_cash
            runway = round(max(0.0, running_balance) / fixed_burn, 1)

            if runway >= 6.0:
                health = "🛡️ Sangat Kuat"
            elif runway >= 3.0:
                health = "🟢 Stabil"
            elif runway >= 1.5:
                health = "⚖️ Ketat"
            else:
                health = "⚠️ Waspada"

            months_forecast.append(
                CashflowMonthForecast(
                    month_name=m_name,
                    month_year=m_y_str,
                    projected_income=total_proj_income,
                    confirmed_invoices_due=confirmed_inv_amount + termin_amount,
                    fixed_burn_rate=estimated_living_spend,
                    projected_net_cashflow=net_cash,
                    projected_ending_balance=running_balance,
                    projected_runway_months=runway,
                    health_status=health,
                )
            )

        # Conservative scenario: No new projects, only existing confirmed invoices
        total_confirmed = sum(inv.amount for inv in unpaid_invoices if inv.status in [InvoiceStatus.UNPAID, InvoiceStatus.OVERDUE])
        conservative_end = max(0.0, current_buffer + total_confirmed - (estimated_living_spend * 3))
        conservative_runway = round(conservative_end / fixed_burn, 1)

        # Strategic Insights
        insights = []
        if conservative_runway >= 3.0:
            insights.append(f"🛡️ *Skenario Terburuk Aman:* Tanpa proyek baru sama sekali, kamu masih bisa bertahan *{conservative_runway} bulan*.")
        else:
            insights.append(f"⚠️ *Skenario Konservatif:* Jika tanpa proyek baru, runway kasmu akan tersisa *{conservative_runway} bulan*. Prioritaskan pipeline klien baru.")

        if total_confirmed > 0:
            insights.append(f"💰 Ada total piutang *{format_currency(total_confirmed, currency)}* yang siap memperkuat kas jika tertagih tepat waktu.")

        if subs_burn > (settings.needs_budget * 0.3):
            insights.append(f"💳 Beban langganan bulananmu cukup tinggi (*{format_currency(subs_burn, currency)}/bln*). Evaluasi software yang jarang dipakai.")

        # Render Telegram Card
        card_lines = [
            f"🔮 *SIMULASI ARUS KAS 90 HARI KEDEPAN*",
            f"━━━━━━━━━━━━━━━━━━━━━",
            f"💵 Saldo Buffer Saat Ini: *{format_currency(current_buffer, currency)}*",
            f"🔥 Pengeluaran Rutin: *{format_currency(estimated_living_spend, currency)} / bulan*\n",
            f"📊 *Proyeksi 3 Bulan Mendatang:*",
        ]

        for m in months_forecast:
            flow_icon = "🟢 +" if m.projected_net_cashflow >= 0 else "🔴 "
            card_lines.append(
                f"• *{m.month_name}:* {m.health_status}\n"
                f"  Inflow: `{format_currency(m.projected_income, currency)}` | Outflow: `{format_currency(m.fixed_burn_rate, currency)}`\n"
                f"  Net: {flow_icon}`{format_currency(m.projected_net_cashflow, currency)}` ➔ Saldo Akhir: `*{format_currency(m.projected_ending_balance, currency)}*` ({m.projected_runway_months} Bln)"
            )

        card_lines.append(f"\n━━━━━━━━━━━━━━━━━━━━━")
        card_lines.append(f"🛡️ *Hasil Skenario 90 Hari:*")
        card_lines.append(f"• 🌟 *Skenario Normal / Optimis:* Saldo Kas ➔ `*{format_currency(running_balance, currency)}*`")
        card_lines.append(f"• 🧱 *Skenario Bertahan (Zero Sales):* Saldo Kas ➔ `*{format_currency(conservative_end, currency)}*` ({conservative_runway} Bln)")
        card_lines.append(f"\n💡 *Catatan Strategis AI:*")
        for ins in insights:
            card_lines.append(f"{ins}")

        summary_card = "\n".join(card_lines)

        return CashflowForecastReport(
            current_buffer_balance=current_buffer,
            current_monthly_burn=estimated_living_spend,
            months=months_forecast,
            optimistic_end_balance=running_balance,
            conservative_end_balance=conservative_end,
            strategic_insights=insights,
            summary_card=summary_card,
        )


cashflow_forecaster = CashflowForecaster()
