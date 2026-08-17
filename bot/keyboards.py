"""
Telegram inline keyboards and reply markups for interactive workflows.
Includes Goal Wishlist, Subscriptions, AI Advisor, and Undo actions.
"""

from typing import List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from database.models import Category, FinancialGoal, Subscription, Quotation, ProjectTermin


def get_quotation_action_keyboard(quotation_id: str) -> InlineKeyboardMarkup:
    """Action buttons for a quotation proposal card."""
    keyboard = [
        [
            InlineKeyboardButton("📄 Unduh PDF SPH", callback_data=f"quote_pdf:{quotation_id}"),
            InlineKeyboardButton("➡️ Konversi ke Invoice", callback_data=f"quote_convert:{quotation_id}"),
        ],
        [
            InlineKeyboardButton("❌ Hapus Penawaran", callback_data=f"quote_del:{quotation_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_quotations_keyboard(quotations: List[Quotation]) -> InlineKeyboardMarkup:
    """Inline keyboard for listing active quotation proposals."""
    buttons = []
    for q in quotations[:6]:
        status_icon = "🟢" if q.status.value == "ACCEPTED" else "📄"
        buttons.append([
            InlineKeyboardButton(f"{status_icon} {q.client_name} - {q.project_title[:18]}", callback_data=f"quote_view:{q.id}"),
            InlineKeyboardButton("📄 PDF", callback_data=f"quote_pdf:{q.id}"),
        ])
    buttons.append([
        InlineKeyboardButton("➕ Buat Penawaran Baru (/quote)", callback_data="quote_help:add"),
    ])
    return InlineKeyboardMarkup(buttons)


def get_termin_action_keyboard(termin_id: str) -> InlineKeyboardMarkup:
    """Action buttons for a project termin card."""
    keyboard = [
        [
            InlineKeyboardButton("🧾 Terbitkan Invoice Termin", callback_data=f"termin_inv:{termin_id}"),
        ],
        [
            InlineKeyboardButton("❌ Hapus Proyek", callback_data=f"termin_del:{termin_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_termins_keyboard(termins: List[ProjectTermin]) -> InlineKeyboardMarkup:
    """Inline keyboard for listing active project termins."""
    buttons = []
    for t in termins[:6]:
        status_icon = "🎉" if t.is_completed else "⏳"
        buttons.append([
            InlineKeyboardButton(f"{status_icon} {t.client_name} ({t.project_title[:18]})", callback_data=f"termin_view:{t.id}"),
            InlineKeyboardButton("🧾 Invoice", callback_data=f"termin_inv:{t.id}"),
        ])
    buttons.append([
        InlineKeyboardButton("➕ Buat Termin Baru (/termin)", callback_data="termin_help:add"),
    ])
    return InlineKeyboardMarkup(buttons)


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Main persistent quick access keyboard with Productivity, Goals, and AI Advisor tools."""
    keyboard = [
        [KeyboardButton("📊 Status Budget"), KeyboardButton("📈 Laporan Bulan Ini")],
        [KeyboardButton("🎯 Target & Goals"), KeyboardButton("💳 Tagihan Rutin")],
        [KeyboardButton("🤖 Tanya AI Advisor"), KeyboardButton("🏆 Skor Keuangan")],
        [KeyboardButton("📄 Surat Penawaran"), KeyboardButton("⏳ Proyek Termin")],
        [KeyboardButton("🧾 Buat Invoice"), KeyboardButton("⏰ Piutang Klien")],
        [KeyboardButton("🔮 Forecast 90 Hari"), KeyboardButton("🛡️ Buffer Runway")],
        [KeyboardButton("📥 Export Excel"), KeyboardButton("⚙️ Pengaturan")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_confirmation_keyboard(pending_id: str) -> InlineKeyboardMarkup:
    """Keyboard for confirming or modifying an AI OCR / NLP extracted transaction."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Simpan (Save)", callback_data=f"tx_confirm:{pending_id}"),
            InlineKeyboardButton("✏️ Ubah Kategori", callback_data=f"tx_cat_menu:{pending_id}"),
        ],
        [
            InlineKeyboardButton("❌ Batalkan (Cancel)", callback_data=f"tx_cancel:{pending_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_category_picker_keyboard(pending_id: str) -> InlineKeyboardMarkup:
    """Keyboard to choose a specific category."""
    keyboard = [
        [
            InlineKeyboardButton("🏠 Needs (Primer)", callback_data=f"tx_set_cat:{pending_id}:Needs"),
            InlineKeyboardButton("☕ Wants (Sekunder)", callback_data=f"tx_set_cat:{pending_id}:Wants"),
        ],
        [
            InlineKeyboardButton("💻 Operational (Kerja)", callback_data=f"tx_set_cat:{pending_id}:Operational"),
            InlineKeyboardButton("📈 Investment", callback_data=f"tx_set_cat:{pending_id}:Investment"),
        ],
        [
            InlineKeyboardButton("🛡️ Buffer / Dana Darurat", callback_data=f"tx_set_cat:{pending_id}:Buffer"),
            InlineKeyboardButton("🔙 Kembali", callback_data=f"tx_back:{pending_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_invoice_action_keyboard(invoice_id: str) -> InlineKeyboardMarkup:
    """Action buttons for an invoice card."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Tandai Lunas (Paid)", callback_data=f"inv_pay:{invoice_id}"),
            InlineKeyboardButton("💬 Draft Pesan WA", callback_data=f"inv_remind:{invoice_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_undo_keyboard(tx_id: str) -> InlineKeyboardMarkup:
    """Inline button to undo/delete recorded transaction with 1 click."""
    keyboard = [
        [
            InlineKeyboardButton("↩️ Batalkan / Hapus Transaksi Ini", callback_data=f"tx_undo:{tx_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_daily_checkin_keyboard() -> InlineKeyboardMarkup:
    """Interactive quick response buttons for evening daily check-in reminder."""
    keyboard = [
        [
            InlineKeyboardButton("➕ Contoh Format Cepat", callback_data="checkin:record"),
            InlineKeyboardButton("🎉 Hari Ini Rp0 (Hemat!)", callback_data="checkin:zero"),
        ],
        [
            InlineKeyboardButton("📊 Cek Status Budget Saat Ini", callback_data="checkin:status"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_goals_keyboard(goals: List[FinancialGoal]) -> InlineKeyboardMarkup:
    """Inline keyboard for list of active goals."""
    buttons = []
    for g in goals[:6]:
        status_icon = "✅" if g.is_completed else "🎯"
        buttons.append([
            InlineKeyboardButton(
                f"{status_icon} {g.name} ({g.percentage_achieved}%)",
                callback_data=f"goal_view:{g.id}",
            ),
            InlineKeyboardButton("❌ Hapus", callback_data=f"goal_del:{g.id}"),
        ])
    buttons.append([
        InlineKeyboardButton("➕ Buat Target Baru (/add_goal)", callback_data="goal_help:add"),
    ])
    return InlineKeyboardMarkup(buttons)


def get_subscriptions_keyboard(subs: List[Subscription]) -> InlineKeyboardMarkup:
    """Inline keyboard for list of recurring subscriptions."""
    buttons = []
    for s in subs[:6]:
        status_icon = "🟢" if s.is_active else "⚪"
        toggle_label = "⏸️ Nonaktif" if s.is_active else "▶️ Aktifkan"
        buttons.append([
            InlineKeyboardButton(f"{status_icon} {s.name} (Tgl {s.billing_day})", callback_data=f"sub_view:{s.id}"),
            InlineKeyboardButton(toggle_label, callback_data=f"sub_toggle:{s.id}"),
            InlineKeyboardButton("❌", callback_data=f"sub_del:{s.id}"),
        ])
    buttons.append([
        InlineKeyboardButton("➕ Tambah Langganan (/add_sub)", callback_data="sub_help:add"),
    ])
    return InlineKeyboardMarkup(buttons)


def get_tax_keyboard() -> InlineKeyboardMarkup:
    """Action buttons for Tax report card."""
    keyboard = [
        [
            InlineKeyboardButton("📑 Unduh PDF SPT Form 1770", callback_data="tax_pdf:export"),
            InlineKeyboardButton("🔄 Ganti Status PTKP", callback_data="tax_ptkp:menu"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_ptkp_selection_keyboard() -> InlineKeyboardMarkup:
    """Selection buttons for PTKP tax status."""
    keyboard = [
        [
            InlineKeyboardButton("TK/0 (Lajang, 0 Tanggungan)", callback_data="ptkp_set:TK0"),
            InlineKeyboardButton("TK/1 (Lajang, 1 Tanggungan)", callback_data="ptkp_set:TK1"),
        ],
        [
            InlineKeyboardButton("K/0 (Menikah, 0 Tanggungan)", callback_data="ptkp_set:K0"),
            InlineKeyboardButton("K/1 (Menikah, 1 Tanggungan)", callback_data="ptkp_set:K1"),
        ],
        [
            InlineKeyboardButton("K/2 (Menikah, 2 Tanggungan)", callback_data="ptkp_set:K2"),
            InlineKeyboardButton("K/3 (Menikah, 3 Tanggungan)", callback_data="ptkp_set:K3"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_currency_keyboard() -> InlineKeyboardMarkup:
    """Action buttons for Currency Rates."""
    keyboard = [
        [
            InlineKeyboardButton("🔄 Refresh Kurs Live", callback_data="curr_refresh:now"),
            InlineKeyboardButton("💡 Bantuan Konversi", callback_data="curr_help:convert"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Main persistent quick access keyboard with Productivity, Goals, and AI Advisor tools."""
    keyboard = [
        [KeyboardButton("📊 Status Budget"), KeyboardButton("📈 Laporan Bulan Ini")],
        [KeyboardButton("🎯 Target & Goals"), KeyboardButton("💳 Tagihan Rutin")],
        [KeyboardButton("🌐 Kurs Valas"), KeyboardButton("🧾 Pajak SPT 1770")],
        [KeyboardButton("⏱️ Hitung Tarif"), KeyboardButton("🔮 Forecast 90 Hari")],
        [KeyboardButton("🤖 Tanya AI Advisor"), KeyboardButton("🏆 Skor Keuangan")],
        [KeyboardButton("🧾 Buat Invoice"), KeyboardButton("⏰ Piutang Klien")],
        [KeyboardButton("🛡️ Buffer Runway"), KeyboardButton("📥 Export Excel")],
        [KeyboardButton("🕒 Riwayat Transaksi"), KeyboardButton("⚙️ Pengaturan")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
