"""
PDF Cheatsheet Generator for Freelance AI Financial Engine.
Produces a sleek, executive-grade reference guide in PDF format.
"""

import os
import io
import logging
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

logger = logging.getLogger(__name__)


def generate_cheatsheet_pdf(output_path: str) -> str:
    """Generate professional PDF Cheatsheet and save to output_path."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()

    # Color Palette
    primary_color = colors.HexColor("#1E293B")  # Deep Slate Navy
    accent_blue = colors.HexColor("#2563EB")    # Royal Blue
    accent_emerald = colors.HexColor("#059669") # Emerald Green
    accent_amber = colors.HexColor("#D97706")   # Amber
    dark_text = colors.HexColor("#0F172A")
    muted_text = colors.HexColor("#64748B")
    table_header_bg = colors.HexColor("#1E293B")
    table_alt_bg = colors.HexColor("#F8FAFC")
    border_color = colors.HexColor("#E2E8F0")

    # Typography Styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=primary_color,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=muted_text,
        spaceAfter=12,
    )
    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=accent_blue,
        spaceBefore=10,
        spaceAfter=6,
    )
    cell_header_style = ParagraphStyle(
        "CellHeader",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        textColor=colors.white,
        alignment=0,
    )
    cell_bold_style = ParagraphStyle(
        "CellBold",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=dark_text,
    )
    cell_code_style = ParagraphStyle(
        "CellCode",
        fontName="Courier-Bold",
        fontSize=8.5,
        leading=11,
        textColor=accent_blue,
    )
    cell_desc_style = ParagraphStyle(
        "CellDesc",
        fontName="Helvetica",
        fontSize=8,
        leading=10.5,
        textColor=dark_text,
    )

    story = []

    # 1. Header & Title Banner
    story.append(Paragraph("Freelance AI Financial Engine", title_style))
    story.append(Paragraph("Panduan Cepat & Kunci Perintah Bot Telegram (Official Reference Cheatsheet)", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=accent_blue, spaceAfter=10))

    # Helper to build section tables
    def build_table(data_rows, col_widths=[140, 160, 200]):
        table_data = []
        for r_idx, row in enumerate(data_rows):
            formatted_row = []
            for c_idx, cell_val in enumerate(row):
                if r_idx == 0:
                    formatted_row.append(Paragraph(cell_val, cell_header_style))
                elif c_idx == 0:
                    formatted_row.append(Paragraph(cell_val, cell_bold_style))
                elif c_idx == 1:
                    formatted_row.append(Paragraph(cell_val, cell_code_style))
                else:
                    formatted_row.append(Paragraph(cell_val, cell_desc_style))
            table_data.append(formatted_row)

        t = Table(table_data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), table_header_bg),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, table_alt_bg]),
            ("GRID", (0, 0), (-1, -1), 0.5, border_color),
        ]))
        return t

    # --- SECTION 1: Target Impian & Wishlist (Goals) ---
    story.append(Paragraph("🎯 1. Target Impian & Wishlist Auto-Split (Goals)", section_heading))
    goals_data = [
        ["Tindakan", "Perintah (Command)", "Contoh / Keterangan"],
        ["Tambah Target", "/add_goal <Nama> <Nominal> <%>", "/add_goal Macbook M3 20jt 10% (Auto-potong 10% saat fee masuk)"],
        ["Lihat Progres & ETA", "/goals atau /wishlist", "Menampilkan progress bar visual & estimasi bulan tercapai"],
        ["Hapus Target", "/delete_goal <ID_Target>", "/delete_goal a1b2c3d4 atau klik tombol hapus di menu"],
    ]
    story.append(build_table(goals_data, [130, 170, 200]))
    story.append(Spacer(1, 6))

    # --- SECTION 2: Langganan Rutin & Fixed Burn Rate ---
    story.append(Paragraph("💳 2. Langganan Rutin & Biaya Tetap (Subscriptions)", section_heading))
    subs_data = [
        ["Tindakan", "Perintah (Command)", "Contoh / Keterangan"],
        ["Tambah Langganan", "/add_sub <Nama> <Nominal> <Tgl>", "/add_sub ChatGPT Plus 300rb 15 (Tagihan setiap tgl 15)"],
        ["Lihat Burn Rate", "/subscriptions atau /subs", "Menghitung total beban biaya operasional tetap per bulan"],
        ["Hapus Langganan", "/delete_sub <ID_Langganan>", "/delete_sub s1a2b3c4 atau klik tombol hapus di bot"],
        ["Pengingat Tagihan", "Otomatis via Bot", "Bot otomatis mengirimkan alert H-3 sebelum jatuh tempo"],
    ]
    story.append(build_table(subs_data, [130, 170, 200]))
    story.append(Spacer(1, 6))

    # --- SECTION 3: Pencatatan Transaksi Harian ---
    story.append(Paragraph("💰 3. Pencatatan Transaksi & Multi-Item", section_heading))
    tx_data = [
        ["Jenis Transaksi", "Format Input", "Contoh Chat di Telegram"],
        ["Pemasukan Proyek", "Ketik nominal fee masuk", "Dapat fee freelance website 5jt (Auto-split ke target & buffer)"],
        ["Pengeluaran 1 Item", "Ketik keperluan + harga", "Makan siang warteg 25k"],
        ["Banyak Item Sekaligus", "Pisahkan dengan koma", "Beli buku 30rb, pensil 5rb, bensin 25k, kopi 18rb"],
        ["Pesan Suara (Voice)", "🎙️ Tahan tombol mic Telegram", "Rekam suara: 'Beli makan malam tiga puluh ribu'"],
        ["1-Click Undo", "Tombol inline di pesan bot", "[ ↩️ Batalkan / Hapus Transaksi Ini ] (Hapus instan dari Sheets)"],
    ]
    story.append(build_table(tx_data, [130, 160, 210]))
    story.append(Spacer(1, 6))

    # --- SECTION 4: AI Financial Advisor & Health Score ---
    story.append(Paragraph("🤖 4. AI Financial Advisor & Skor Kesehatan", section_heading))
    ai_data = [
        ["Fitur", "Perintah (Command)", "Contoh / Keterangan"],
        ["Konsultasi AI", "/advisor <Pertanyaan>", "/advisor apakah aman kalau saya beli iPad 8jt bulan ini?"],
        ["Pemicu Bahasa Alami", "tanya: <Pertanyaan>", "tanya: evaluasi pengeluaran dan sisa budget saya"],
        ["Skor Kesehatan (0-100)", "/health atau /score", "Evaluasi 4 pilar: Buffer Runway, Tabungan, Disiplin, & Pajak"],
    ]
    story.append(build_table(ai_data, [130, 160, 210]))
    story.append(Spacer(1, 6))

    # --- SECTION 5: Invoicing & Piutang Klien ---
    story.append(Paragraph("🧾 5. Invoice Generator & Piutang Klien", section_heading))
    inv_data = [
        ["Fitur", "Perintah (Command)", "Contoh / Keterangan"],
        ["Buat Invoice PDF", "/invoice", "Dipandu pembuatan invoice PDF profesional dalam hitungan detik"],
        ["Daftar Piutang", "/unpaid atau /invoices", "Melihat seluruh tagihan belum lunas & status jatuh tempo"],
        ["Tandai Lunas", "/pay_invoice <ID_Invoice>", "Atau cukup ketik: 'Invoice INV-260817-ABC lunas'"],
        ["Draft Pesan WA", "/remind_invoice <ID_Invoice>", "Membuat template teks penagihan sopan siap kirim ke WhatsApp"],
    ]
    story.append(build_table(inv_data, [130, 170, 200]))
    story.append(Spacer(1, 6))

    # --- SECTION 6: Penawaran Harga (SPH) & Proyek Termin ---
    story.append(Paragraph("📑 6. Penawaran Harga (Quotation/SPH) & Proyek Termin", section_heading))
    quote_data = [
        ["Fitur / Dokumen", "Perintah (Command)", "Contoh / Keterangan"],
        ["Buat SPH Resmi (PDF)", "/quote <Klien> | <Proyek> | <Nominal> | <Durasi>", "/quote PT Maju Jaya | Redesign Website | 15jt | 14 Hari Kerja (PDF resmi langsung jadi)"],
        ["Daftar Penawaran", "/quotes atau /sph", "Melihat seluruh penawaran aktif & konversi 1-klik ke invoice saat deal"],
        ["Daftar Proyek Termin", "/termin <Klien> | <Proyek> | <Nominal> | <%>", "/termin Studio XYZ | Mobile App | 20jt | 50% 30% 20% (Kelola DP & termin)"],
        ["Tagih Invoice Termin", "/termins", "Menerbitkan invoice resmi per tahapan termin dengan 1 klik"],
    ]
    story.append(build_table(quote_data, [130, 170, 200]))
    story.append(Spacer(1, 6))

    # --- SECTION 7: Radar Belanja & Forecast 90 Hari ---
    story.append(Paragraph("🎯 7. Radar Belanja ('Boleh Beli?') & Forecast 90 Hari", section_heading))
    radar_data = [
        ["Fitur Analisis", "Perintah (Command)", "Contoh / Keterangan"],
        ["Radar Boleh Beli?", "/beli <Nama Barang> <Harga>", "/beli PS5 Slim 7.5jt (Analisis kuota Wants, Runway & status lampu 🟢/🟡/🔴)"],
        ["Simulasi Kas 90 Hari", "/forecast atau /proyeksi", "Proyeksi arus kas 3 bulan ke depan, piutang masuk, dan skenario bertahan"],
    ]
    story.append(build_table(radar_data, [130, 170, 200]))
    story.append(Spacer(1, 6))

    # --- SECTION 8: Kurs Valas, Pajak SPT 1770, & Hitung Tarif ---
    story.append(Paragraph("🌐 8. Kurs Valas Realtime, Pajak SPT 1770 & Hitung Tarif", section_heading))
    fx_tax_data = [
        ["Fitur Mutakhir", "Perintah (Command)", "Contoh / Keterangan"],
        ["Kurs Valas Realtime", "/kurs atau /convert", "/kurs (Tabel live USD, EUR, SGD, GBP, JPY, USDT) atau /convert 500 USD upwork"],
        ["Simulasi Pajak Freelance", "/pajak atau /tax", "/pajak (Hitung PPh 21 Norma NPPN 50%, PTKP TK/0 - K/3, & PPh 17 progresif)"],
        ["Download Form 1770 PDF", "/export_spt", "Unduh dokumen PDF Rekapitulasi Peredaran Bruto resmi siap lapor DJP Online"],
        ["Kalkulator Tarif Proyek", "/rate atau /hitung_harga", "/rate Redesign Web 30 jam (AI hitung 3 tier: Batas Bawah, Standar, Premium)"],
    ]
    story.append(build_table(fx_tax_data, [130, 170, 200]))
    story.append(Spacer(1, 6))

    # --- SECTION 9: Laporan, Budget, & Parameter Pengaturan ---
    story.append(Paragraph("📊 9. Laporan, Budget & Pengaturan Parameter", section_heading))
    set_data = [
        ["Fitur / Pengaturan", "Perintah (Command)", "Nilai Default / Contoh"],
        ["Status & Jajan Aman", "/status", "Cek sisa kuota Needs, Wants, & batas jajan harian"],
        ["Laporan Visual Bulanan", "/report", "Ringkasan bulanan + grafik pie chart otomatis"],
        ["Dana Cadangan Buffer", "/buffer", "Menghitung kekuatan bulan bertahan hidup (Runway)"],
        ["Tarik Saldo Buffer", "/draw_buffer <Nominal>", "/draw_buffer 1000000 (Saat membutuhkan dana darurat)"],
        ["Export Excel / PDF", "/export atau /pdf", "Download spreadsheet .xlsx atau laporan eksekutif .pdf"],
        ["Target Gaji Pokok", "/set_salary <Nominal>", "/set_salary 10000000 (Gaji minimum bulanan)"],
        ["Pajak & Cadangan Ops", "/set_tax <Persen>", "/set_tax 10 (Persentase cadangan pajak)"],
        ["Limit Budget Needs", "/set_needs <Nominal>", "/set_needs 5000000 (Batas kebutuhan pokok)"],
        ["Limit Budget Wants", "/set_wants <Nominal>", "/set_wants 2500000 (Batas keinginan/hiburan)"],
        ["Limit Budget Ops", "/set_ops <Nominal>", "/set_ops 1500000 (Batas operasional kerja)"],
        ["Nama di Invoice/SPH", "/set_name <Nama>", "/set_name Budi Pratama"],
        ["Rekening Pembayaran", "/set_bank <Info>", "/set_bank BCA 123-456-7890 a/n Budi"],
    ]
    story.append(build_table(set_data, [130, 170, 200]))

    # Build document
    doc.build(story)
    logger.info("PDF Cheatsheet successfully generated at %s", output_path)
    return output_path


if __name__ == "__main__":
    out_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Panduan_Kunci_Freelance_Finance.pdf")
    generate_cheatsheet_pdf(out_file)
    print(f"PDF Generated successfully: {out_file}")
