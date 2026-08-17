"""
Hourly Rate (MAR) & Smart Project Pricing Calculator Engine.
Calculates freelancer's Minimum Acceptable Rate (MAR) based on cost of living, taxes, operational software costs,
and billable hours. Provides 3-tier project estimation (Floor, Recommended, Value-Based Premium).
"""

import math
import logging
from typing import List, Optional
from datetime import datetime

from config import format_currency
from database.models import UserSettings, PricingTier, PricingEstimateReport

logger = logging.getLogger(__name__)


class PricingCalculatorEngine:
    @staticmethod
    def calculate_minimum_hourly_rate(settings: UserSettings) -> float:
        """
        Calculate Minimum Acceptable Rate (MAR) per billable hour.
        Formula:
        Total Monthly Cost = Target Salary + Needs + Wants + Ops + Tax Reserve (10%) + Emergency/Buffer (15%)
        Monthly Billable Hours = Weekly Billable Hours * 4.2 (approx 4.2 weeks per month)
        MAR = Total Monthly Cost / Monthly Billable Hours
        """
        weekly_hours = max(10.0, settings.weekly_billable_hours or 30.0)
        monthly_hours = weekly_hours * 4.2

        monthly_living_cost = settings.target_salary or 10_000_000.0
        monthly_ops = settings.operational_budget or 1_500_000.0
        monthly_tax = monthly_living_cost * (settings.tax_percentage / 100.0 if settings.tax_percentage else 0.10)
        monthly_buffer_savings = monthly_living_cost * 0.15  # 15% savings rate

        total_monthly_need = monthly_living_cost + monthly_ops + monthly_tax + monthly_buffer_savings
        hourly_mar = total_monthly_need / monthly_hours

        # Round up to clean thousand e.g. Rp 115.000 / hour
        return math.ceil(hourly_mar / 5000.0) * 5000.0

    @classmethod
    def calculate_project_pricing(
        cls,
        project_title: str,
        estimated_hours: float,
        settings: UserSettings,
        complexity_level: str = "Medium",
    ) -> PricingEstimateReport:
        """
        Calculates 3-tier project quotation based on hourly MAR and complexity.
        """
        hours = max(1.0, estimated_hours)
        mar = cls.calculate_minimum_hourly_rate(settings)

        # Multiplier by complexity
        complexity_mult = {"Simple": 1.0, "Medium": 1.15, "Complex": 1.35}.get(complexity_level.capitalize(), 1.15)
        adjusted_base_rate = mar * complexity_mult

        # Tier 1: Floor Price (Breakeven / Impas)
        floor_total = math.ceil((adjusted_base_rate * hours) / 50000.0) * 50000.0
        tier_floor = PricingTier(
            tier_name="Floor Price (Batas Bawah)",
            tier_badge="🛡️ Batas Bawah (Modal Kerja)",
            total_price=floor_total,
            effective_hourly_rate=round(floor_total / hours, 0),
            profit_margin_percent=0.0,
            description="Harga terendah agar tidak rugi modal waktu & biaya operasional. Jangan tawar di bawah ini!",
        )

        # Tier 2: Recommended Market Price (Wajar Pasar - Margin 35%)
        rec_total = math.ceil((floor_total * 1.35) / 50000.0) * 50000.0
        tier_rec = PricingTier(
            tier_name="Recommended (Standar Pasar)",
            tier_badge="🎯 Standar Pasar (Rekomendasi)",
            total_price=rec_total,
            effective_hourly_rate=round(rec_total / hours, 0),
            profit_margin_percent=35.0,
            description="Harga ideal & kompetitif untuk klien reguler. Sudah termasuk cadangan revisi minor 2x.",
        )

        # Tier 3: Value-Based Premium Price (Klien Korporat / High Margin 75%)
        prem_total = math.ceil((floor_total * 1.75) / 50000.0) * 50000.0
        tier_prem = PricingTier(
            tier_name="Premium Value-Based",
            tier_badge="💎 Value-Based Premium (Korporat)",
            total_price=prem_total,
            effective_hourly_rate=round(prem_total / hours, 0),
            profit_margin_percent=75.0,
            description="Harga untuk klien korporat / bisnis besar dengan urgensi tinggi, prioritas SLA, dan garansi.",
        )

        currency = settings.currency or "IDR"

        summary_card = (
            f"⏱️ *KALKULATOR TARIF & HARGA PROYEK*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Proyek: *{project_title}*\n"
            f"⏳ Estimasi Waktu: *{hours:g} Jam Kerja* (Kompleksitas: _{complexity_level}_)\n"
            f"🛡️ Tarif Dasar Min (MAR): `*{format_currency(mar, currency)}/jam*`\n\n"
            f"📊 *3 PILIHAN STRATEGI HARGA (PRICING TIERS):*\n\n"
            f"1. {tier_floor.tier_badge}\n"
            f"   💰 Total: `*{format_currency(tier_floor.total_price, currency)}*` (`{format_currency(tier_floor.effective_hourly_rate, currency)}/jam`)\n"
            f"   📝 _{tier_floor.description}_\n\n"
            f"2. {tier_rec.tier_badge}\n"
            f"   💰 Total: `*{format_currency(tier_rec.total_price, currency)}*` (`{format_currency(tier_rec.effective_hourly_rate, currency)}/jam`)\n"
            f"   📝 _{tier_rec.description}_\n\n"
            f"3. {tier_prem.tier_badge}\n"
            f"   💰 Total: `*{format_currency(tier_prem.total_price, currency)}*` (`{format_currency(tier_prem.effective_hourly_rate, currency)}/jam`)\n"
            f"   📝 _{tier_prem.description}_\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 _Langsung buat penawaran resmi dengan ketik:_ \n`/quote <Klien> | {project_title} | {format_currency(tier_rec.total_price, currency)}`"
        )

        scope_recs = [
            f"Terapkan aturan DP minimal 50% ({format_currency(tier_rec.total_price * 0.5, currency)}) sebelum mulai bekerja.",
            "Cantumkan batasan maksimal 2x revisi minor dalam surat penawaran harga.",
            "Tentukan timeline jelas (misal 5 jam/hari = selesai dalam " + str(math.ceil(hours / 5.0)) + " hari kerja).",
        ]

        return PricingEstimateReport(
            project_title=project_title,
            estimated_hours=hours,
            complexity_level=complexity_level,
            minimum_hourly_rate=mar,
            target_monthly_salary=settings.target_salary,
            living_cost_per_hour=round(settings.target_salary / (settings.weekly_billable_hours * 4.2), 0),
            tiers=[tier_floor, tier_rec, tier_prem],
            scope_recommendations=scope_recs,
            summary_card=summary_card,
        )


# Singleton instance
pricing_calculator = PricingCalculatorEngine()
