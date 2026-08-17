"""
PDF Quotation / Surat Penawaran Harga (SPH) Generator using ReportLab.
Produces sleek, minimalist, executive-grade PDF Quotations directly in memory.
"""

import io
import logging
from typing import Optional, List
from datetime import datetime

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
    KeepTogether,
)

from config import format_currency
from database.models import Quotation, QuotationItem, UserSettings

logger = logging.getLogger(__name__)


class PDFQuotationGenerator:
    """Generates modern, minimalist PDF quotation proposals / Surat Penawaran Harga."""

    @staticmethod
    def generate_pdf(
        quotation: Quotation,
        user_settings: Optional[UserSettings] = None,
    ) -> bytes:
        """Render quotation data to PDF bytes buffer."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()

        # Custom Palette: Emerald Navy Accent
        primary_color = colors.HexColor("#0F766E")  # Deep Emerald Teal
        dark_text = colors.HexColor("#1E293B")
        muted_text = colors.HexColor("#64748B")
        light_bg = colors.HexColor("#F0FDFA")
        border_color = colors.HexColor("#CCFBF1")

        title_style = ParagraphStyle(
            "QuotationTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=primary_color,
        )
        subtitle_style = ParagraphStyle(
            "QuotationSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=muted_text,
        )
        heading_style = ParagraphStyle(
            "SectionHeading",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=primary_color,
        )
        body_style = ParagraphStyle(
            "BodyDark",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=dark_text,
        )
        body_bold = ParagraphStyle(
            "BodyDarkBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=13,
            textColor=dark_text,
        )
        table_header_style = ParagraphStyle(
            "TableHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=colors.white,
        )
        table_cell_style = ParagraphStyle(
            "TableCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=dark_text,
        )
        table_cell_right = ParagraphStyle(
            "TableCellRight",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            alignment=2,
            textColor=dark_text,
        )

        currency = quotation.currency
        freelancer_name = user_settings.freelancer_name if user_settings else "Freelance Professional"
        payment_info = user_settings.payment_details if user_settings else "Bank Transfer"

        story = []

        # 1. Header: Freelancer vs Document Info
        header_data = [
            [
                Paragraph(f"<b>{freelancer_name}</b>", body_bold),
                Paragraph("<b>SURAT PENAWARAN HARGA (SPH)</b>", title_style),
            ],
            [
                Paragraph("Professional Creative & Tech Services", subtitle_style),
                Paragraph(f"No. Dokumen: <b>{quotation.id}</b>", subtitle_style),
            ],
            [
                Paragraph("", subtitle_style),
                Paragraph(f"Tanggal Terbit: <b>{quotation.issue_date}</b>", subtitle_style),
            ],
            [
                Paragraph("", subtitle_style),
                Paragraph(f"Berlaku Hingga: <b>{quotation.valid_until}</b>", subtitle_style),
            ],
        ]

        t_header = Table(header_data, colWidths=[240, 240])
        t_header.setStyle(TableStyle([
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(t_header)
        story.append(Spacer(1, 15))
        story.append(HRFlowable(width="100%", thickness=1, color=border_color, spaceAfter=15))

        # 2. Client & Proposal Scope
        client_data = [
            [
                Paragraph("<b>Ditujukan Kepada Klien:</b>", heading_style),
                Paragraph("<b>Ringkasan Proyek:</b>", heading_style),
            ],
            [
                Paragraph(f"<b>{quotation.client_name}</b>", body_bold),
                Paragraph(f"<b>{quotation.project_title}</b>", body_bold),
            ],
            [
                Paragraph(f"Email: {quotation.client_email or '-'}", body_style),
                Paragraph(f"Estimasi Pengerjaan: <b>{quotation.timeline}</b>", body_style),
            ],
            [
                Paragraph("", body_style),
                Paragraph(f"Ketentuan Revisi: <b>{quotation.revision_limit}</b>", body_style),
            ],
        ]

        t_client = Table(client_data, colWidths=[240, 240])
        t_client.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t_client)
        story.append(Spacer(1, 20))

        # 3. Line Items Table
        items_table_data = [
            [
                Paragraph("No.", table_header_style),
                Paragraph("Rincian Pekerjaan / Deliverables", table_header_style),
                Paragraph("Kuantitas", table_header_style),
                Paragraph("Harga Satuan", table_header_style),
                Paragraph("Total Harga", table_header_style),
            ]
        ]

        if quotation.items:
            for idx, item in enumerate(quotation.items, start=1):
                items_table_data.append([
                    Paragraph(str(idx), table_cell_style),
                    Paragraph(item.description, table_cell_style),
                    Paragraph(f"{item.quantity:g}", table_cell_style),
                    Paragraph(format_currency(item.rate, currency), table_cell_right),
                    Paragraph(format_currency(item.amount, currency), table_cell_right),
                ])
        else:
            items_table_data.append([
                Paragraph("1", table_cell_style),
                Paragraph(quotation.project_title, table_cell_style),
                Paragraph("1", table_cell_style),
                Paragraph(format_currency(quotation.amount, currency), table_cell_right),
                Paragraph(format_currency(quotation.amount, currency), table_cell_right),
            ])

        t_items = Table(items_table_data, colWidths=[30, 220, 60, 85, 85])
        t_items.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), primary_color),
            ("ALIGN", (0, 0), (2, -1), "LEFT"),
            ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, light_bg]),
            ("GRID", (0, 0), (-1, -1), 0.5, border_color),
        ]))
        story.append(t_items)
        story.append(Spacer(1, 10))

        # 4. Total Amount Block
        summary_table_data = [
            [
                Paragraph("<b>TOTAL ESTIMASI BIAYA:</b>", body_bold),
                Paragraph(f"<b>{format_currency(quotation.amount, currency)}</b>", ParagraphStyle(
                    "TotalStyle",
                    parent=table_cell_right,
                    fontName="Helvetica-Bold",
                    fontSize=13,
                    textColor=primary_color,
                )),
            ]
        ]
        t_summary = Table(summary_table_data, colWidths=[330, 150])
        t_summary.setStyle(TableStyle([
            ("ALIGN", (0, 0), (0, -1), "RIGHT"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t_summary)
        story.append(Spacer(1, 15))

        # 5. Terms, DP Rules & Agreement Box
        notes_story = [
            Paragraph("<b>KETENTUAN & SYARAT KERJASAMA (TERMS OF SERVICE):</b>", heading_style),
            Spacer(1, 4),
            Paragraph(f"• <b>Skema Pembayaran:</b> {quotation.dp_terms}", body_style),
            Paragraph(f"• <b>Batas Revisi:</b> {quotation.revision_limit}. Revisi di luar kesepakatan akan dikenakan biaya tambahan.", body_style),
            Paragraph(f"• <b>Masa Berlaku:</b> Penawaran ini berlaku hingga tanggal <b>{quotation.valid_until}</b>.", body_style),
            Paragraph(f"• <b>Rekening Pembayaran:</b> {payment_info}", body_style),
        ]
        if quotation.notes:
            notes_story.append(Paragraph(f"• <b>Catatan Tambahan:</b> {quotation.notes}", body_style))

        notes_box = Table([[notes_story]], colWidths=[480])
        notes_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), light_bg),
            ("BOX", (0, 0), (-1, -1), 1, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(KeepTogether(notes_box))
        story.append(Spacer(1, 25))

        # 6. Signature / Approval Confirmation
        sig_data = [
            [
                Paragraph("Disetujui Oleh (Klien):<br/><br/><br/><br/>_______________________<br/><b>" + quotation.client_name + "</b>", body_style),
                Paragraph("Hormat Kami (Penyedia Jasa):<br/><br/><br/><br/>_______________________<br/><b>" + freelancer_name + "</b>", body_style),
            ]
        ]
        t_sig = Table(sig_data, colWidths=[240, 240])
        t_sig.setStyle(TableStyle([
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(KeepTogether(t_sig))

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()


quotation_generator = PDFQuotationGenerator()
