"""
PDF Invoice Generator using ReportLab.
Produces sleek, minimalist, professional PDF invoices directly in memory.
"""

import io
import logging
from typing import Optional, List
from datetime import datetime

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
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
from database.models import Invoice, InvoiceItem, UserSettings

logger = logging.getLogger(__name__)


class PDFInvoiceGenerator:
    """Generates modern, minimalist PDF invoices."""

    @staticmethod
    def generate_pdf(
        invoice: Invoice,
        user_settings: Optional[UserSettings] = None,
    ) -> bytes:
        """Render invoice data to PDF bytes buffer."""
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
        
        # Custom Paragraph Styles
        primary_color = colors.HexColor("#1E3A8A")  # Royal Navy Blue
        dark_text = colors.HexColor("#1E293B")
        muted_text = colors.HexColor("#64748B")
        light_bg = colors.HexColor("#F8FAFC")
        border_color = colors.HexColor("#E2E8F0")

        title_style = ParagraphStyle(
            "InvoiceTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=28,
            textColor=primary_color,
        )

        subtitle_style = ParagraphStyle(
            "InvoiceSubtitle",
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

        story = []

        # --- 1. Header Section ---
        freelancer_name = user_settings.freelancer_name if user_settings else "Freelance Professional"
        currency = invoice.currency

        header_data = [
            [
                Paragraph(f"<b>{freelancer_name}</b>", title_style),
                Paragraph("<b>INVOICE RESMI</b>", ParagraphStyle("RightTitle", parent=title_style, alignment=2, fontSize=20, textColor=primary_color)),
            ],
            [
                Paragraph("Layanan Profesional & Pengembangan Solusi Digital", subtitle_style),
                Paragraph(f"<b>No:</b> {invoice.id}", ParagraphStyle("RightSub", parent=subtitle_style, alignment=2, textColor=dark_text)),
            ],
        ]

        header_table = Table(header_data, colWidths=[10 * cm, 7 * cm])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 15))
        story.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=15))

        # --- 2. Client & Metadata Section ---
        meta_data = [
            [
                Paragraph("<b>DITUJUKAN KEPADA (BILL TO):</b>", heading_style),
                Paragraph("<b>INFORMASI TAGIHAN:</b>", heading_style),
            ],
            [
                Paragraph(f"<b>{invoice.client_name}</b><br/>{invoice.client_email or 'Klien Terhormat'}<br/><b>Proyek:</b> {invoice.project_title}", body_style),
                Paragraph(
                    f"<b>Tanggal Terbit:</b> {invoice.issue_date}<br/>"
                    f"<b>Jatuh Tempo:</b> <font color='#DC2626'><b>{invoice.due_date}</b></font><br/>"
                    f"<b>Status:</b> {invoice.status.value}",
                    body_style,
                ),
            ],
        ]

        meta_table = Table(meta_data, colWidths=[10 * cm, 7 * cm])
        meta_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, -1), light_bg),
            ("BOX", (0, 0), (-1, -1), 0.5, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 20))

        # --- 3. Items Table ---
        items_data = [
            [
                Paragraph("<b>No</b>", table_header_style),
                Paragraph("<b>Deskripsi Layanan / Scope of Work</b>", table_header_style),
                Paragraph("<b>Qty</b>", ParagraphStyle("QtyH", parent=table_header_style, alignment=1)),
                Paragraph("<b>Harga Satuan</b>", ParagraphStyle("RateH", parent=table_header_style, alignment=2)),
                Paragraph("<b>Total</b>", ParagraphStyle("TotH", parent=table_header_style, alignment=2)),
            ]
        ]

        if not invoice.items:
            # Single item fallback from project title
            items_data.append([
                Paragraph("1", table_cell_style),
                Paragraph(invoice.project_title, table_cell_style),
                Paragraph("1", ParagraphStyle("QtyC", parent=table_cell_style, alignment=1)),
                Paragraph(format_currency(invoice.amount, currency), table_cell_right),
                Paragraph(format_currency(invoice.amount, currency), table_cell_right),
            ])
        else:
            for idx, item in enumerate(invoice.items, start=1):
                items_data.append([
                    Paragraph(str(idx), table_cell_style),
                    Paragraph(item.description, table_cell_style),
                    Paragraph(f"{item.quantity:g}", ParagraphStyle("QtyC", parent=table_cell_style, alignment=1)),
                    Paragraph(format_currency(item.rate, currency), table_cell_right),
                    Paragraph(format_currency(item.amount, currency), table_cell_right),
                ])

        items_table = Table(items_data, colWidths=[1 * cm, 8.5 * cm, 1.8 * cm, 2.8 * cm, 2.9 * cm])
        items_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), primary_color),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("BOX", (0, 0), (-1, -1), 0.5, border_color),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
        ]))
        story.append(items_table)
        story.append(Spacer(1, 15))

        # --- 4. Total & Payment Info Box ---
        payment_info = (
            user_settings.payment_details
            if (user_settings and user_settings.payment_details)
            else (invoice.payment_info or "Transfer Bank BCA: 123-456-7890 a/n Freelancer")
        )

        summary_data = [
            [
                Paragraph("<b>INSTRUKSI PEMBAYARAN:</b>", heading_style),
                Paragraph("<b>TOTAL TAGIHAN:</b>", ParagraphStyle("TotLabel", parent=heading_style, alignment=2)),
            ],
            [
                Paragraph(
                    f"Silakan lakukan transfer ke rekening berikut:<br/>"
                    f"<b>{payment_info}</b><br/>"
                    f"<i>Harap sertakan No. Invoice ({invoice.id}) pada berita transfer.</i>",
                    body_style,
                ),
                Paragraph(
                    f"<font size=14 color='#1E3A8A'><b>{format_currency(invoice.amount, currency)}</b></font><br/>"
                    f"<font size=8 color='#64748B'>Sudah termasuk seluruh kesepakatan scope</font>",
                    ParagraphStyle("GrandTot", parent=body_bold, alignment=2),
                ),
            ],
        ]

        summary_table = Table(summary_data, colWidths=[10 * cm, 7 * cm])
        summary_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, -1), light_bg),
            ("BOX", (0, 0), (-1, -1), 0.5, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(KeepTogether(summary_table))
        story.append(Spacer(1, 30))

        # --- 5. Footer / Signature ---
        footer_text = (
            f"Terima kasih atas kerja samanya! Invoice ini diterbitkan secara sah dan otomatis oleh <b>Freelance AI Financial Engine</b>."
        )
        story.append(Paragraph(footer_text, ParagraphStyle("Footer", parent=subtitle_style, alignment=1, fontSize=8)))

        # Build PDF
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes


invoice_generator = PDFInvoiceGenerator()
