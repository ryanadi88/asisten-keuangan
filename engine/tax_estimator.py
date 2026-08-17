"""
AI Tax Estimator & SPT Tahunan Form 1770 Generator Engine.
Implements Indonesian Tax Laws (UU HPP & PP 55/2022) for Freelancers & Solopreneurs:
- Norma Penghitungan Penghasilan Neto (NPPN 50% Pekerja Bebas)
- PTKP (Penghasilan Tidak Kena Pajak) TK/0 s.d K/3
- PPh Pasal 17 Progressive Tax Brackets (5%, 15%, 25%, 30%, 35%)
- PPh Final UMKM 0.5% Threshold (Rp 500 Juta non-taxable threshold)
- Rekapitulasi Peredaran Bruto Bulanan siap lapor DJP Online.
"""

import calendar
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from config import format_currency
from database.models import (
    UserSettings,
    MonthlySummary,
    PTKPStatus,
    TaxMethod,
    MonthlyRevenueRow,
    TaxBracketDetail,
    TaxCalculationReport,
)

logger = logging.getLogger(__name__)

# PTKP Values in IDR (Standard DJP Online)
PTKP_VALUES: Dict[PTKPStatus, float] = {
    PTKPStatus.TK0: 54_000_000.0,
    PTKPStatus.TK1: 58_500_000.0,
    PTKPStatus.TK2: 63_000_000.0,
    PTKPStatus.TK3: 67_500_000.0,
    PTKPStatus.K0: 58_500_000.0,
    PTKPStatus.K1: 63_000_000.0,
    PTKPStatus.K2: 67_500_000.0,
    PTKPStatus.K3: 72_000_000.0,
}

INDONESIAN_MONTHS = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"
]


class TaxEstimatorEngine:
    @staticmethod
    def get_ptkp_amount(status: PTKPStatus) -> float:
        return PTKP_VALUES.get(status, 54_000_000.0)

    @classmethod
    def calculate_progressive_pph21(cls, pkp: float) -> Tuple[float, List[TaxBracketDetail]]:
        """Calculate progressive tax according to UU HPP Pasal 17 brackets."""
        if pkp <= 0:
            return 0.0, []

        brackets = [
            ("Lapisan 1 (5% s.d Rp 60 Juta)", 60_000_000.0, 0.05),
            ("Lapisan 2 (15% Rp 60 - 250 Juta)", 190_000_000.0, 0.15),   # 250 - 60 = 190
            ("Lapisan 3 (25% Rp 250 - 500 Juta)", 250_000_000.0, 0.25),  # 500 - 250 = 250
            ("Lapisan 4 (30% Rp 500 Jt - 5 Miliar)", 4_500_000_000.0, 0.30),
            ("Lapisan 5 (35% di atas Rp 5 Miliar)", float("inf"), 0.35),
        ]

        total_tax = 0.0
        remaining_pkp = pkp
        bracket_details: List[TaxBracketDetail] = []

        for name, max_slice, rate in brackets:
            if remaining_pkp <= 0:
                break

            slice_amount = min(remaining_pkp, max_slice)
            tax_for_slice = slice_amount * rate
            total_tax += tax_for_slice
            remaining_pkp -= slice_amount

            bracket_details.append(
                TaxBracketDetail(
                    bracket_name=name,
                    taxable_slice=slice_amount,
                    rate_percent=rate * 100.0,
                    tax_amount=tax_for_slice,
                )
            )

        return round(total_tax, 2), bracket_details

    @classmethod
    def calculate_annual_tax_report(
        cls,
        year: int,
        all_monthly_summaries: List[MonthlySummary],
        settings: UserSettings,
        method: TaxMethod = TaxMethod.NPPN_FREELANCE,
    ) -> TaxCalculationReport:
        """
        Calculates annual freelance tax projection, PTKP deductions, and builds DJP Form 1770 table.
        """
        ptkp_status = settings.ptkp_status or PTKPStatus.TK0
        ptkp_amount = cls.get_ptkp_amount(ptkp_status)
        nppn_rate = settings.nppn_rate or 50.0  # default 50%

        # Build 12-month revenue rows
        summaries_by_month: Dict[str, float] = {}
        for s in all_monthly_summaries:
            if s.month_year.startswith(str(year)):
                summaries_by_month[s.month_year] = s.total_income

        monthly_rows: List[MonthlyRevenueRow] = []
        actual_months_incomes = []

        for m_idx in range(1, 13):
            m_str = f"{year}-{m_idx:02d}"
            m_name = f"{INDONESIAN_MONTHS[m_idx-1]} {year}"

            if m_str in summaries_by_month:
                gross = summaries_by_month[m_str]
                is_proj = False
                actual_months_incomes.append(gross)
            else:
                # If current or past month with 0, or future month -> project based on average
                avg_inc = (sum(actual_months_incomes) / len(actual_months_incomes)) if actual_months_incomes else settings.target_salary
                gross = round(avg_inc, 2)
                is_proj = True

            net = round(gross * (nppn_rate / 100.0), 2)
            monthly_rows.append(
                MonthlyRevenueRow(
                    month_name=m_name,
                    month_year=m_str,
                    gross_income=gross,
                    nppn_rate=nppn_rate,
                    net_income=net,
                    is_projected=is_proj,
                )
            )

        total_annual_gross = sum(r.gross_income for r in monthly_rows)
        total_annual_net = sum(r.net_income for r in monthly_rows)

        if method == TaxMethod.NPPN_FREELANCE:
            pkp_amount = max(0.0, total_annual_net - ptkp_amount)
            total_tax, brackets = cls.calculate_progressive_pph21(pkp_amount)
        else:
            # PPh Final UMKM 0.5% (PP 55/2022 threshold: omzet s.d 500jt bebas pajak)
            taxable_gross = max(0.0, total_annual_gross - 500_000_000.0)
            total_tax = round(taxable_gross * 0.005, 2)
            pkp_amount = taxable_gross
            brackets = [
                TaxBracketDetail(
                    bracket_name="PPh Final PP 55 (0.5% di atas Rp 500 Juta)",
                    taxable_slice=taxable_gross,
                    rate_percent=0.5,
                    tax_amount=total_tax,
                )
            ]

        monthly_installment = round(total_tax / 12.0, 2)
        effective_rate = round((total_tax / total_annual_gross * 100.0), 2) if total_annual_gross > 0 else 0.0

        # Build Telegram Summary Card
        bracket_lines = "\n".join([
            f"   • *{b.bracket_name}:* `{format_currency(b.tax_amount, 'IDR')}`"
            for b in brackets
        ]) if brackets else "   • Nihil (Di bawah PTKP)"

        summary_card = (
            f"🧾 *SIMULASI & REKAP PAJAK SPT FREELANCE ({year})*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Wajib Pajak: *{settings.freelancer_name}*\n"
            f"📋 Skema: *Norma NPPN {nppn_rate:g}% (Pekerja Bebas)*\n"
            f"👥 Status PTKP: *{ptkp_status.value}* (`{format_currency(ptkp_amount, 'IDR')}`)\n\n"
            f"💰 *Total Omzet Bruto (1 Tahun):* `{format_currency(total_annual_gross, 'IDR')}`\n"
            f"📉 *Penghasilan Neto ({nppn_rate:g}%):* `{format_currency(total_annual_net, 'IDR')}`\n"
            f"✂️ *PTKP Bebas Pajak:* `-{format_currency(ptkp_amount, 'IDR')}`\n"
            f"⚖️ *Penghasilan Kena Pajak (PKP):* `*{format_currency(pkp_amount, 'IDR')}*`\n\n"
            f"📊 *Rincian Tarif Progresif PPh 21:*\n{bracket_lines}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 *Total PPh Terutang Setahun:* `*{format_currency(total_tax, 'IDR')}*`\n"
            f"💵 *Estimasi Cicilan PPh 25/Bulan:* `{format_currency(monthly_installment, 'IDR')}`\n"
            f"📈 *Tarif Pajak Efektif:* `{effective_rate}% dari Omzet`\n\n"
            f"💡 Ketik `/export_spt` untuk mengunduh dokumen PDF Rekapitulasi Form 1770 resmi DJP Online!"
        )

        djp_guide = (
            "📌 *Panduan Pengisian SPT Tahunan di DJP Online (Form 1770):*\n"
            "1. Buka situs djponline.pajak.go.id lalu login.\n"
            "2. Pilih menu e-Form SPT 1770.\n"
            "3. Pada Lampiran III (Peredaran Bruto), salin tabel omzet bulanan dari dokumen PDF ini.\n"
            "4. Masukkan Penghasilan Neto dan centang tarif Norma NPPN 50%.\n"
            "5. Pastikan status PTKP sesuai dengan akun Anda."
        )

        return TaxCalculationReport(
            tax_year=year,
            tax_method=method,
            ptkp_status=ptkp_status,
            ptkp_amount=ptkp_amount,
            total_annual_gross=total_annual_gross,
            total_annual_net=total_annual_net,
            pkp_amount=pkp_amount,
            brackets=brackets,
            total_tax_due=total_tax,
            monthly_tax_installment=monthly_installment,
            effective_tax_rate=effective_rate,
            monthly_breakdown=monthly_rows,
            summary_card=summary_card,
            djp_filling_guide=djp_guide,
        )


# Singleton instance
tax_estimator = TaxEstimatorEngine()
