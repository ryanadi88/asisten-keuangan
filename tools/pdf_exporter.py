"""
PDF Financial Statement & Report Exporter using ReportLab.
Generates comprehensive PDF financial statements for Telegram Bot exports.
"""

import io
import logging
from datetime import datetime
from typing import Optional, List

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)

from config import format_currency, get_current_month_year
from database.models import (
    MonthlySummary,
    UserSettings,
    Transaction,
    TransactionType,
    FinancialGoal,
    Subscription,
)

logger = logging.getLogger(__name__)


class PDFFinancialExporter:
    """Generates clean executive-grade PDF financial statements."""

    @staticmethod
    def generate_statement_pdf(
        user_id: int,
        month_year: str,
        summary: MonthlySummary,
        settings: UserSettings,
        transactions: List[Transaction],
        goals: List[FinancialGoal],
        subscriptions: List[Subscription],
    ) -> bytes:
        """Render complete financial statement into PDF bytes buffer."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.5 * cm,
            leftMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
        )

        styles = getSampleStyleSheet()
        primary_color = colors.HexColor("#1E293B")
        accent_blue = colors.HexColor("#2563EB")
        accent_green = colors.HexColor("#059669")
        accent_red = colors.HexColor("#DC2626")
        muted_text = colors.HexColor("#64748B")
        border_color = colors.HexColor("#E2E8F0")

        title_style = ParagraphStyle(
            "StatementTitle",
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=primary_color,
        )
        subtitle_style = ParagraphStyle(
            "StatementSubtitle",
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=muted_text,
        )
        section_style = ParagraphStyle(
            "SectionHeader",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=accent_blue,
            spaceBefore=8,
            spaceAfter=4,
        )
        cell_head = ParagraphStyle(
            "CellHead",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            textColor=colors.white,
        )
        cell_text = ParagraphStyle(
            "CellText",
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#0F172A"),
        )
        cell_bold = ParagraphStyle(
            "CellBold",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#0F172A"),
        )

        currency = settings.currency
        story = []

        # 1. Header Banner
        story.append(Paragraph(f"LAPORAN KEUANGAN FREELANCE — {month_year}", title_style))
        story.append(Paragraph(f"Freelancer: <b>{settings.freelancer_name}</b> | Dibuat: {datetime.now().strftime('%d %B %Y %H:%M')}", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=accent_blue, spaceAfter=8))

        # 2. Executive Summary Metrics (Table)
        story.append(Paragraph("📊 Ringkasan Eksekutif Bulan Ini", section_style))
        surplus = summary.total_income - summary.total_expense
        runway = summary.buffer_runway_months

        metric_data = [
            [
                Paragraph("<b>Total Pemasukan:</b>", cell_text),
                Paragraph(f"<font color='#059669'><b>{format_currency(summary.total_income, currency)}</b></font>", cell_text),
                Paragraph("<b>Cadangan Pajak (10%):</b>", cell_text),
                Paragraph(f"{format_currency(summary.tax_reserve, currency)}", cell_text),
            ],
            [
                Paragraph("<b>Total Pengeluaran:</b>", cell_text),
                Paragraph(f"<font color='#DC2626'><b>{format_currency(summary.total_expense, currency)}</b></font>", cell_text),
                Paragraph("<b>Gaji Pokok Ditarik:</b>", cell_text),
                Paragraph(f"{format_currency(summary.actual_salary_drawn, currency)} / {format_currency(summary.target_salary, currency)}", cell_text),
            ],
            [
                Paragraph("<b>Surplus / Net Tabungan:</b>", cell_text),
                Paragraph(f"<b>{format_currency(surplus, currency)}</b>", cell_text),
                Paragraph("<b>Saldo Buffer & Runway:</b>", cell_text),
                Paragraph(f"<b>{format_currency(summary.buffer_fund_balance, currency)}</b> ({runway} Bln)", cell_text),
            ],
        ]
        t_metric = Table(metric_data, colWidths=[130, 130, 130, 130])
        t_metric.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("GRID", (0, 0), (-1, -1), 0.5, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t_metric)
        story.append(Spacer(1, 6))

        # 3. Active Goals
        if goals:
            story.append(Paragraph("🎯 Target Impian & Wishlist (Active Goals)", section_style))
            g_rows = [
                [Paragraph("Target", cell_head), Paragraph("Terkumpul", cell_head), Paragraph("Target", cell_head), Paragraph("Alokasi", cell_head), Paragraph("Progres", cell_head)]
            ]
            for g in goals[:6]:
                g_rows.append([
                    Paragraph(g.name, cell_bold),
                    Paragraph(format_currency(g.current_amount, currency), cell_text),
                    Paragraph(format_currency(g.target_amount, currency), cell_text),
                    Paragraph(f"{g.allocation_percent}%", cell_text),
                    Paragraph(f"{g.percentage_achieved:.1f}%", cell_bold),
                ])
            t_goals = Table(g_rows, colWidths=[150, 100, 100, 70, 100])
            t_goals.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("GRID", (0, 0), (-1, -1), 0.5, border_color),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ]))
            story.append(t_goals)
            story.append(Spacer(1, 6))

        # 4. Recurring Subscriptions
        if subscriptions:
            story.append(Paragraph("💳 Langganan Rutin & Biaya Tetap (Subscriptions)", section_style))
            s_rows = [
                [Paragraph("Layanan", cell_head), Paragraph("Biaya / Bulan", cell_head), Paragraph("Jatuh Tempo", cell_head), Paragraph("Kategori", cell_head), Paragraph("Status", cell_head)]
            ]
            for s in subscriptions[:6]:
                status_str = "🟢 Aktif" if s.is_active else "⚪ Nonaktif"
                s_rows.append([
                    Paragraph(s.name, cell_bold),
                    Paragraph(format_currency(s.amount, currency), cell_text),
                    Paragraph(f"Tgl {s.billing_day}", cell_text),
                    Paragraph(s.category.value, cell_text),
                    Paragraph(status_str, cell_text),
                ])
            t_subs = Table(s_rows, colWidths=[150, 110, 80, 100, 80])
            t_subs.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("GRID", (0, 0), (-1, -1), 0.5, border_color),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ]))
            story.append(t_subs)
            story.append(Spacer(1, 6))

        # 5. Recent Transactions
        story.append(Paragraph("🕒 Riwayat Transaksi Terakhir", section_style))
        tx_rows = [
            [Paragraph("Tanggal", cell_head), Paragraph("Tipe", cell_head), Paragraph("Kategori", cell_head), Paragraph("Deskripsi", cell_head), Paragraph("Nominal", cell_head)]
        ]
        for tx in transactions[:15]:
            type_color = "#059669" if tx.type == TransactionType.INCOME else "#DC2626"
            tx_rows.append([
                Paragraph(tx.timestamp.strftime("%d/%m/%Y"), cell_text),
                Paragraph(f"<font color='{type_color}'><b>{tx.type.value}</b></font>", cell_text),
                Paragraph(tx.category.value, cell_text),
                Paragraph(tx.source_or_merchant, cell_text),
                Paragraph(format_currency(tx.amount, currency), cell_bold),
            ])
        t_tx = Table(tx_rows, colWidths=[70, 70, 90, 180, 110])
        t_tx.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
            ("GRID", (0, 0), (-1, -1), 0.5, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ]))
        story.append(t_tx)

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def generate_spt_tax_report_pdf(
        report: "TaxCalculationReport",
        settings: UserSettings,
    ) -> bytes:
        """Generate official DJP Form 1770 Annual Tax Statement PDF."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.5 * cm,
            leftMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
        )

        styles = getSampleStyleSheet()
        primary_color = colors.HexColor("#1E293B")
        accent_blue = colors.HexColor("#0F766E")  # Teal Emerald
        muted_text = colors.HexColor("#64748B")
        border_color = colors.HexColor("#CBD5E1")

        title_style = ParagraphStyle(
            "SPTTitle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=primary_color,
            alignment=1,
        )
        subtitle_style = ParagraphStyle(
            "SPTSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=muted_text,
            alignment=1,
        )
        section_style = ParagraphStyle(
            "SPTSection",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=primary_color,
            spaceBefore=10,
            spaceAfter=5,
        )
        cell_head = ParagraphStyle("SPTHead", fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white, alignment=0)
        cell_text = ParagraphStyle("SPTCell", fontName="Helvetica", fontSize=8, textColor=primary_color)
        cell_bold = ParagraphStyle("SPTCellB", fontName="Helvetica-Bold", fontSize=8.5, textColor=primary_color)
        cell_right = ParagraphStyle("SPTCellR", fontName="Helvetica", fontSize=8, textColor=primary_color, alignment=2)
        cell_right_b = ParagraphStyle("SPTCellRB", fontName="Helvetica-Bold", fontSize=8.5, textColor=primary_color, alignment=2)

        story = []

        # Header
        story.append(Paragraph(f"REKAPITULASI PEREDARAN BRUTO & PERHITUNGAN PPh", title_style))
        story.append(Paragraph(f"LAMPIRAN SPT TAHUNAN ORANG PRIBADI FORM 1770 — TAHUN PAJAK {report.tax_year}", subtitle_style))
        story.append(Spacer(1, 4))
        story.append(HRFlowable(width="100%", thickness=1.5, color=accent_blue, spaceBefore=4, spaceAfter=8))

        # Taxpayer Details Table
        taxpayer_info = [
            [Paragraph("<b>Nama Wajib Pajak:</b>", cell_text), Paragraph(settings.freelancer_name, cell_bold), Paragraph("<b>Tahun Pajak:</b>", cell_text), Paragraph(str(report.tax_year), cell_bold)],
            [Paragraph("<b>Klasifikasi Lapangan Usaha:</b>", cell_text), Paragraph("Pekerja Bebas / Konsultan / IT & Desain", cell_text), Paragraph("<b>Metode Pajak:</b>", cell_text), Paragraph(report.tax_method.value, cell_bold)],
            [Paragraph("<b>Status PTKP:</b>", cell_text), Paragraph(f"{report.ptkp_status.value} ({format_currency(report.ptkp_amount, 'IDR')})", cell_bold), Paragraph("<b>Tarif Norma (NPPN):</b>", cell_text), Paragraph("50% (Penghasilan Neto)", cell_bold)],
        ]
        t_info = Table(taxpayer_info, colWidths=[130, 160, 100, 130])
        t_info.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("GRID", (0, 0), (-1, -1), 0.5, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t_info)
        story.append(Spacer(1, 8))

        # Monthly Revenue Table (Lampiran III DJP Form 1770)
        story.append(Paragraph("📑 1. Rekapitulasi Peredaran Bruto Bulanan (DJP Form 1770 Lampiran III)", section_style))
        rev_rows = [
            [Paragraph("No", cell_head), Paragraph("Bulan", cell_head), Paragraph("Peredaran Bruto (Rp)", cell_head), Paragraph("Tarif Norma", cell_head), Paragraph("Penghasilan Neto (Rp)", cell_head)]
        ]
        for idx, row in enumerate(report.monthly_breakdown, start=1):
            proj_mark = " <i>(Proyeksi)</i>" if row.is_projected else ""
            rev_rows.append([
                Paragraph(str(idx), cell_text),
                Paragraph(row.month_name + proj_mark, cell_text),
                Paragraph(format_currency(row.gross_income, "IDR"), cell_right),
                Paragraph(f"{row.nppn_rate:g}%", cell_text),
                Paragraph(format_currency(row.net_income, "IDR"), cell_right),
            ])
        # Summary Row
        rev_rows.append([
            Paragraph("<b>TOTAL</b>", cell_bold),
            Paragraph("<b>Akumulasi 1 Tahun</b>", cell_bold),
            Paragraph(f"<b>{format_currency(report.total_annual_gross, 'IDR')}</b>", cell_right_b),
            Paragraph("<b>50%</b>", cell_bold),
            Paragraph(f"<b>{format_currency(report.total_annual_net, 'IDR')}</b>", cell_right_b),
        ])

        t_rev = Table(rev_rows, colWidths=[25, 145, 130, 80, 140])
        t_rev.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F766E")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E2E8F0")),
            ("GRID", (0, 0), (-1, -1), 0.5, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAFC")]),
        ]))
        story.append(t_rev)
        story.append(Spacer(1, 8))

        # Tax Computation Section
        story.append(Paragraph("⚖️ 2. Perhitungan PPh Terutang (UU HPP Pasal 17)", section_style))
        comp_rows = [
            [Paragraph("Komponen Perhitungan", cell_head), Paragraph("Dasar Pengenaan Pajak", cell_head), Paragraph("Tarif Pajak", cell_head), Paragraph("Jumlah PPh (Rp)", cell_head)],
            [Paragraph("Penghasilan Neto Setahun", cell_text), Paragraph(format_currency(report.total_annual_net, "IDR"), cell_right), Paragraph("-", cell_text), Paragraph("-", cell_right)],
            [Paragraph(f"Penghasilan Tidak Kena Pajak ({report.ptkp_status.value})", cell_text), Paragraph(f"- {format_currency(report.ptkp_amount, 'IDR')}", cell_right), Paragraph("-", cell_text), Paragraph("-", cell_right)],
            [Paragraph("<b>Penghasilan Kena Pajak (PKP)</b>", cell_bold), Paragraph(f"<b>{format_currency(report.pkp_amount, 'IDR')}</b>", cell_right_b), Paragraph("-", cell_text), Paragraph("-", cell_right)],
        ]
        for b in report.brackets:
            comp_rows.append([
                Paragraph(b.bracket_name, cell_text),
                Paragraph(format_currency(b.taxable_slice, "IDR"), cell_right),
                Paragraph(f"{b.rate_percent:g}%", cell_text),
                Paragraph(format_currency(b.tax_amount, "IDR"), cell_right),
            ])
        comp_rows.append([
            Paragraph("<b>TOTAL PPh TERUTANG (SETARIF TAHUNAN)</b>", cell_bold),
            Paragraph("-", cell_text),
            Paragraph(f"<b>{report.effective_tax_rate}% (Efektif)</b>", cell_bold),
            Paragraph(f"<b><font color='#0F766E'>{format_currency(report.total_tax_due, 'IDR')}</font></b>", cell_right_b),
        ])
        comp_rows.append([
            Paragraph("<b>Estimasi Angsuran PPh Pasal 25 per Bulan</b>", cell_bold),
            Paragraph("-", cell_text),
            Paragraph("Dibagi 12 Bulan", cell_text),
            Paragraph(f"<b>{format_currency(report.monthly_tax_installment, 'IDR')}</b>", cell_right_b),
        ])

        t_comp = Table(comp_rows, colWidths=[190, 120, 90, 120])
        t_comp.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
            ("BACKGROUND", (0, -2), (-1, -1), colors.HexColor("#F1F5F9")),
            ("GRID", (0, 0), (-1, -1), 0.5, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -3), [colors.white, colors.HexColor("#F8FAFC")]),
        ]))
        story.append(t_comp)

        # Footer notes
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "<i>Catatan: Dokumen ini disusun otomatis berdasarkan UU No. 7 Tahun 2021 (UU Harmonisasi Peraturan Perpajakan) "
            "dan PER-17/PJ/2015 tentang Norma Penghitungan Penghasilan Neto bagi Pekerja Bebas. Nilai peredaran bruto dapat disalin langsung ke e-Form SPT 1770 DJP Online.</i>",
            subtitle_style
        ))

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()


pdf_financial_exporter = PDFFinancialExporter()
