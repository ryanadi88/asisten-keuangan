"""
Instant Affordability Radar Engine ("Boleh Beli Nggak?").
Analyzes prospective discretionary purchases against live freelance cashflow, Wants budget, and Buffer runway.
"""

import calendar
import logging
from typing import Optional, List
from datetime import datetime

from config import format_currency
from database.models import (
    MonthlySummary,
    UserSettings,
    FinancialGoal,
    Subscription,
    AffordabilityReport,
    AffordabilityRating,
)

logger = logging.getLogger(__name__)


class AffordabilityRadar:
    """Evaluates purchase safety against freelance budget constraints."""

    @staticmethod
    def evaluate_purchase(
        item_name: str,
        price: float,
        summary: MonthlySummary,
        settings: UserSettings,
        wants_spent: float = 0.0,
        active_goals: Optional[List[FinancialGoal]] = None,
        active_subs: Optional[List[Subscription]] = None,
    ) -> AffordabilityReport:
        """Calculate math metrics and return actionable verdict report."""
        currency = settings.currency
        today = datetime.now()
        _, last_day = calendar.monthrange(today.year, today.month)
        days_left = max(1, last_day - today.day + 1)

        # 1. Wants Budget Analysis
        wants_remaining_before = max(0.0, settings.wants_budget - wants_spent)
        wants_remaining_after = wants_remaining_before - price

        # 2. Runway & Buffer Analysis
        subs_total = sum(s.amount for s in active_subs) if active_subs else 0.0
        monthly_burn = settings.needs_budget + subs_total
        if monthly_burn <= 0:
            monthly_burn = 5_000_000.0

        buffer_balance = summary.buffer_fund_balance
        runway_before = round(buffer_balance / monthly_burn, 1)

        # Excess cost above wants budget dips into buffer
        excess_draw = max(0.0, price - wants_remaining_before)
        new_buffer = max(0.0, buffer_balance - excess_draw)
        runway_after = round(new_buffer / monthly_burn, 1)

        # 3. Daily Safe Spend
        daily_before = max(0.0, wants_remaining_before / days_left)
        daily_after = max(0.0, max(0.0, wants_remaining_after) / days_left)

        # 4. Impact on Goals
        goals_delay_text = None
        if active_goals and price >= 500_000:
            top_goal = active_goals[0]
            pct_of_goal = round((price / top_goal.target_amount) * 100.0, 1)
            goals_delay_text = (
                f"Nominal {format_currency(price, currency)} ini setara dengan *{pct_of_goal}%* "
                f"dari target impianmu: *{top_goal.name}* ({format_currency(top_goal.target_amount, currency)})."
            )

        # 5. Rating & Verdict Decision Matrix
        recs = []
        if price <= wants_remaining_before and runway_before >= 3.0:
            rating = AffordabilityRating.GREEN
            badge = "🟢 SANGAT AMAN / GO AHEAD!"
            title = "Aman Dibeli! Keuanganmu Dalam Kondisi Sehat"
            recs.append("✅ Kuota jajan (Wants) bulan ini masih mencukupi.")
            recs.append(f"✅ Runway dana cadanganmu tetap aman di level *{runway_before} bulan*.")
            recs.append(f"💡 Sisa kuota Wants setelah dibeli: *{format_currency(wants_remaining_after, currency)}*.")
        elif runway_after >= 3.0 and price <= (settings.wants_budget * 2.5):
            rating = AffordabilityRating.YELLOW
            badge = "🟡 PERTIMBANGKAN / BUTUH PENGHEMATAN"
            title = "Bisa Dibeli, Tapi Kuota Jajan Bulan Ini Akan Minus"
            recs.append(f"⚠️ Pembelian ini melebihi sisa kuota Wants sebesar *{format_currency(excess_draw, currency)}*.")
            recs.append(f"⚠️ Sisa jajan harianmu turun dari `{format_currency(daily_before, currency)}/hari` menjadi `Rp0/hari`.")
            recs.append(f"💡 Runway dana daruratmu masih relatif aman (*{runway_after} bulan*), tapi kamu harus rem pengeluaran non-pokok sampai akhir bulan.")
        else:
            rating = AffordabilityRating.RED
            badge = "🔴 TUNDA DULU / BAHAYA UNTUK RUNWAY"
            title = "Jangan Beli Sekarang! Berisiko Tinggi Bagi Keuangan"
            recs.append(f"⛔ Runway dana daruratmu akan terpangkas menjadi *{runway_after} bulan* (Batas aman: 3-6 bulan).")
            recs.append("⛔ Arus kas freelancer fluktuatif, membeli barang ini sekarang berisiko membuatmu panik jika ada paceklik proyek.")
            recs.append(f"💡 Masukkan barang ini ke target impian dengan perintah: `/add_goal {item_name} {int(price)} 10%` agar terbeli otomatis tanpa mengorbankan dana darurat.")

        # Render Telegram Summary Card
        card_lines = [
            f"🎯 *RADAR KELAYAKAN BELANJA: {item_name.upper()}*",
            f"━━━━━━━━━━━━━━━━━━━━━",
            f"🏷️ Harga Barang: *{format_currency(price, currency)}*",
            f"📊 Status Kelayakan: {badge}\n",
            f"*{title}*\n",
            f"🔍 *Analisis Dampak Finansial:*",
            f"• 🛍️ Kuota Wants: `{format_currency(wants_remaining_before, currency)}` ➔ `*{format_currency(wants_remaining_after, currency)}*`",
            f"• 🛡️ Buffer Runway: `{runway_before} Bulan` ➔ `*{runway_after} Bulan*`",
            f"• ☕ Batas Jajan/Hari: `{format_currency(daily_before, currency)}` ➔ `*{format_currency(daily_after, currency)}*`",
        ]

        if goals_delay_text:
            card_lines.append(f"• 🎯 Komparasi Wishlist: {goals_delay_text}")

        card_lines.append("\n💡 *Rekomendasi Penasihat:*")
        for r in recs:
            card_lines.append(f"{r}")

        summary_card = "\n".join(card_lines)

        return AffordabilityReport(
            item_name=item_name,
            price=price,
            rating=rating,
            verdict_title=title,
            verdict_badge=badge,
            wants_budget_remaining_before=wants_remaining_before,
            wants_budget_remaining_after=wants_remaining_after,
            runway_months_before=runway_before,
            runway_months_after=runway_after,
            daily_safe_spend_before=daily_before,
            daily_safe_spend_after=daily_after,
            goals_delay_impact=goals_delay_text,
            recommendations=recs,
            summary_card=summary_card,
        )


affordability_radar = AffordabilityRadar()
