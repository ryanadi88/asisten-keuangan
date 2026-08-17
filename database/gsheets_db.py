"""
Google Sheets storage backend using gspread and google-auth.
Provides free, collaborative cloud persistence directly in Google Drive.
Features separate Income and Expenses worksheets with executive-grade formatting.
"""

import os
import uuid
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import gspread
from google.oauth2.service_account import Credentials

from config import settings
from database.base import StorageBackend
from database.models import (
    Transaction,
    TransactionCreate,
    TransactionType,
    Category,
    MonthlySummary,
    UserSettings,
    Invoice,
    InvoiceCreate,
    InvoiceItem,
    InvoiceStatus,
    FinancialGoal,
    FinancialGoalCreate,
    Subscription,
    SubscriptionCreate,
    Quotation,
    QuotationCreate,
    QuotationItem,
    QuotationStatus,
    ProjectTermin,
    ProjectTerminCreate,
    ProjectMilestone,
    MilestoneStatus,
)

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

TX_HEADERS = [
    "id",
    "user_id",
    "timestamp",
    "type",
    "category",
    "amount",
    "source_or_merchant",
    "receipt_url",
    "notes",
]

SUMMARY_HEADERS = [
    "month_year",
    "user_id",
    "total_income",
    "total_expense",
    "target_salary",
    "actual_salary_drawn",
    "buffer_fund_balance",
    "emergency_fund",
    "investment_total",
    "tax_reserve",
]

SETTINGS_HEADERS = [
    "user_id",
    "target_salary",
    "tax_percentage",
    "needs_budget",
    "wants_budget",
    "operational_budget",
    "emergency_target",
    "currency",
    "freelancer_name",
    "payment_details",
]

INVOICE_HEADERS = [
    "id",
    "user_id",
    "client_name",
    "client_email",
    "project_title",
    "amount",
    "currency",
    "issue_date",
    "due_date",
    "status",
    "items_json",
    "payment_info",
    "notes",
    "paid_date",
]

GOAL_HEADERS = [
    "id",
    "user_id",
    "name",
    "target_amount",
    "current_amount",
    "progress_%",
    "allocation_percent",
    "is_completed",
    "created_at",
    "target_date",
]

SUBSCRIPTION_HEADERS = [
    "id",
    "user_id",
    "name",
    "amount",
    "billing_cycle",
    "billing_day",
    "category",
    "is_active",
]

QUOTATION_HEADERS = [
    "id",
    "user_id",
    "client_name",
    "client_email",
    "project_title",
    "amount",
    "currency",
    "issue_date",
    "valid_until",
    "timeline",
    "revision_limit",
    "dp_terms",
    "status",
    "items_json",
    "notes",
    "converted_invoice_id",
]

TERMIN_HEADERS = [
    "id",
    "user_id",
    "client_name",
    "project_title",
    "total_amount",
    "currency",
    "milestones_json",
    "created_at",
    "is_completed",
]


def _clean_float(val: Any, default: float = 0.0) -> float:
    """Safely convert numbers or formatted currency/percentage strings (e.g. 'Rp4.000.000', '10.0%') to float."""
    if val is None or val == "":
        return default
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).replace("Rp", "").replace("IDR", "").replace("%", "").replace(".", "").replace(",", "").strip()
    try:
        return float(val_str)
    except (ValueError, TypeError):
        return default


class GoogleSheetsBackend(StorageBackend):
    def __init__(
        self,
        credentials_file: Optional[str] = None,
        spreadsheet_key: Optional[str] = None,
    ):
        self.credentials_file = credentials_file or settings.GOOGLE_SHEETS_CREDENTIALS_FILE
        self.spreadsheet_key = spreadsheet_key or settings.GOOGLE_SPREADSHEET_KEY
        self._client: Optional[gspread.Client] = None
        self._spreadsheet: Optional[gspread.Spreadsheet] = None

    def _get_client(self) -> gspread.Client:
        if self._client is not None:
            return self._client

        if not os.path.exists(self.credentials_file):
            raise FileNotFoundError(
                f"Google Sheets credentials file '{self.credentials_file}' not found. "
                "Please provide a valid service account JSON file or switch DB_BACKEND to 'sqlite'."
            )

        creds = Credentials.from_service_account_file(
            self.credentials_file,
            scopes=SCOPES,
        )
        self._client = gspread.authorize(creds)
        return self._client

    def _get_spreadsheet(self) -> gspread.Spreadsheet:
        if self._spreadsheet is not None:
            return self._spreadsheet

        client = self._get_client()
        key_or_title = self.spreadsheet_key.strip()

        try:
            if key_or_title.startswith("https://docs.google.com/spreadsheets/"):
                self._spreadsheet = client.open_by_url(key_or_title)
            elif len(key_or_title) > 30 and " " not in key_or_title and "/" not in key_or_title:
                self._spreadsheet = client.open_by_key(key_or_title)
            else:
                self._spreadsheet = client.open(key_or_title)
        except gspread.SpreadsheetNotFound:
            try:
                logger.info("Spreadsheet '%s' not found. Creating a new one...", key_or_title)
                self._spreadsheet = client.create(key_or_title)
            except Exception as e:
                service_email = getattr(client.auth, "service_account_email", "Service Account Email")
                raise FileNotFoundError(
                    f"\n[!] Google Spreadsheet '{key_or_title}' tidak ditemukan atau belum dibagikan!\n"
                    f"👉 Langkah penyelesaian:\n"
                    f"1. Buka Google Sheets di browser dan buat spreadsheet baru dengan nama: '{key_or_title}'\n"
                    f"2. Klik tombol 'Share' (Bagikan) di pojok kanan atas.\n"
                    f"3. Masukkan email Service Account: {service_email}\n"
                    f"4. Pilih peran sebagai 'Editor' dan klik Send/Simpan."
                ) from e

        return self._spreadsheet

    def _sync_init_db(self) -> None:
        sh = self._get_spreadsheet()

        # 1. Income Worksheet
        try:
            ws_inc = sh.worksheet("Income")
        except gspread.WorksheetNotFound:
            ws_inc = sh.add_worksheet(title="Income", rows=1000, cols=len(TX_HEADERS))
            ws_inc.append_row(TX_HEADERS)

        if not ws_inc.row_values(1):
            ws_inc.append_row(TX_HEADERS)

        # 2. Expenses Worksheet
        try:
            ws_exp = sh.worksheet("Expenses")
        except gspread.WorksheetNotFound:
            ws_exp = sh.add_worksheet(title="Expenses", rows=1000, cols=len(TX_HEADERS))
            ws_exp.append_row(TX_HEADERS)

        if not ws_exp.row_values(1):
            ws_exp.append_row(TX_HEADERS)

        # 3. Migrate from old unified 'Transactions' worksheet if present
        try:
            ws_old = sh.worksheet("Transactions")
            old_records = ws_old.get_all_values()
            if len(old_records) > 1:
                # Row 0 is header, rows 1.. are data
                for row in old_records[1:]:
                    if len(row) >= 4:
                        tx_type = str(row[3]).upper().strip()
                        if tx_type == "INCOME":
                            ws_inc.append_row(row)
                        else:
                            ws_exp.append_row(row)
                logger.info("Migrated %d rows from old Transactions to Income and Expenses.", len(old_records) - 1)
            sh.del_worksheet(ws_old)
        except gspread.WorksheetNotFound:
            pass

        # 4. Monthly Summary Worksheet
        try:
            ws_sum = sh.worksheet("Monthly_Summary")
        except gspread.WorksheetNotFound:
            ws_sum = sh.add_worksheet(title="Monthly_Summary", rows=500, cols=len(SUMMARY_HEADERS))
            ws_sum.append_row(SUMMARY_HEADERS)

        # 5. Settings Worksheet
        try:
            ws_set = sh.worksheet("Settings")
        except gspread.WorksheetNotFound:
            ws_set = sh.add_worksheet(title="Settings", rows=100, cols=len(SETTINGS_HEADERS))
            ws_set.append_row(SETTINGS_HEADERS)

        # 6. Invoices Worksheet
        try:
            ws_inv = sh.worksheet("Invoices")
        except gspread.WorksheetNotFound:
            ws_inv = sh.add_worksheet(title="Invoices", rows=500, cols=len(INVOICE_HEADERS))
            ws_inv.append_row(INVOICE_HEADERS)

        # 7. Goals & Wishlist Worksheet
        try:
            ws_goal = sh.worksheet("Goals_Wishlist")
        except gspread.WorksheetNotFound:
            ws_goal = sh.add_worksheet(title="Goals_Wishlist", rows=200, cols=len(GOAL_HEADERS))
            ws_goal.append_row(GOAL_HEADERS)

        # 8. Recurring Subscriptions Worksheet
        try:
            ws_sub = sh.worksheet("Subscriptions")
        except gspread.WorksheetNotFound:
            ws_sub = sh.add_worksheet(title="Subscriptions", rows=200, cols=len(SUBSCRIPTION_HEADERS))
            ws_sub.append_row(SUBSCRIPTION_HEADERS)

        # 9. Quotations / Surat Penawaran Harga Worksheet
        try:
            ws_quote = sh.worksheet("Quotations")
        except gspread.WorksheetNotFound:
            ws_quote = sh.add_worksheet(title="Quotations", rows=300, cols=len(QUOTATION_HEADERS))
            ws_quote.append_row(QUOTATION_HEADERS)

        # 10. Project Termins & Milestones Worksheet
        try:
            ws_termin = sh.worksheet("Termins_Milestones")
        except gspread.WorksheetNotFound:
            ws_termin = sh.add_worksheet(title="Termins_Milestones", rows=300, cols=len(TERMIN_HEADERS))
            ws_termin.append_row(TERMIN_HEADERS)

        # 11. Clean up default empty Sheet1 if present
        try:
            ws_default = sh.worksheet("Sheet1")
            if len(sh.worksheets()) > 1:
                sh.del_worksheet(ws_default)
        except gspread.WorksheetNotFound:
            pass

        # 12. Apply Executive Professional UI Styling
        try:
            from tools.sheet_styler import apply_professional_styling
            apply_professional_styling(sh)
        except Exception as e:
            logger.warning("Failed to auto-apply professional sheet styling: %s", e)

        logger.info("Google Sheets initialized with Income, Expenses, Goals, and Subscriptions: %s", sh.url)

    async def init_db(self) -> None:
        await asyncio.to_thread(self._sync_init_db)

    # --- Transactions (Income & Expenses) ---

    def _sync_add_transaction(self, tx: TransactionCreate) -> Transaction:
        sh = self._get_spreadsheet()
        ws_name = "Income" if tx.type == TransactionType.INCOME else "Expenses"
        ws = sh.worksheet(ws_name)
        tx_id = str(uuid.uuid4())[:8]
        row = [
            tx_id,
            str(tx.user_id),
            tx.timestamp.isoformat(),
            tx.type.value,
            tx.category.value,
            float(tx.amount),
            tx.source_or_merchant,
            tx.receipt_url or "",
            tx.notes or "",
        ]
        ws.append_row(row)
        return Transaction(
            id=tx_id,
            user_id=tx.user_id,
            timestamp=tx.timestamp,
            type=tx.type,
            category=tx.category,
            amount=tx.amount,
            source_or_merchant=tx.source_or_merchant,
            receipt_url=tx.receipt_url,
            notes=tx.notes,
        )

    async def add_transaction(self, tx: TransactionCreate) -> Transaction:
        return await asyncio.to_thread(self._sync_add_transaction, tx)

    def _sync_get_transaction_by_id(self, tx_id: str, user_id: int) -> Optional[Transaction]:
        sh = self._get_spreadsheet()
        for ws_name in ["Expenses", "Income"]:
            try:
                ws = sh.worksheet(ws_name)
                records = ws.get_all_records()
                for r in records:
                    if str(r.get("id")) == str(tx_id) and int(r.get("user_id", 0)) == user_id:
                        return Transaction(
                            id=str(r["id"]),
                            user_id=int(r["user_id"]),
                            timestamp=datetime.fromisoformat(str(r["timestamp"])),
                            type=TransactionType(r["type"]),
                            category=Category(r["category"]),
                            amount=float(r["amount"]),
                            source_or_merchant=str(r.get("source_or_merchant", "")),
                            receipt_url=str(r.get("receipt_url", "")) or None,
                            notes=str(r.get("notes", "")) or None,
                        )
            except Exception as e:
                logger.warning("Error searching in %s: %s", ws_name, e)
        return None

    async def get_transaction_by_id(self, tx_id: str, user_id: int) -> Optional[Transaction]:
        return await asyncio.to_thread(self._sync_get_transaction_by_id, tx_id, user_id)

    def _sync_delete_transaction(self, tx_id: str, user_id: int) -> bool:
        sh = self._get_spreadsheet()
        for ws_name in ["Expenses", "Income"]:
            try:
                ws = sh.worksheet(ws_name)
                cell = ws.find(tx_id)
                if cell:
                    row_vals = ws.row_values(cell.row)
                    if len(row_vals) > 1 and int(row_vals[1]) == user_id:
                        ws.delete_rows(cell.row)
                        return True
            except Exception as e:
                logger.warning("Error deleting in %s: %s", ws_name, e)
        return False

    async def delete_transaction(self, tx_id: str, user_id: int) -> bool:
        return await asyncio.to_thread(self._sync_delete_transaction, tx_id, user_id)

    def _sync_get_transactions(
        self,
        user_id: int,
        month_year: Optional[str] = None,
        limit: int = 50,
    ) -> List[Transaction]:
        sh = self._get_spreadsheet()
        all_txs: List[Transaction] = []

        for ws_name in ["Expenses", "Income"]:
            try:
                ws = sh.worksheet(ws_name)
                records = ws.get_all_records()
                for r in records:
                    if int(r.get("user_id", 0)) != user_id:
                        continue
                    ts = str(r.get("timestamp", ""))
                    if month_year and not ts.startswith(month_year):
                        continue
                    try:
                        # Clean currency strings if formatted as RpX.XXX
                        raw_amt = str(r.get("amount", 0.0)).replace("Rp", "").replace(".", "").replace(",", "").strip()
                        amount_val = float(raw_amt) if raw_amt else 0.0

                        all_txs.append(
                            Transaction(
                                id=str(r.get("id")),
                                user_id=int(r.get("user_id")),
                                timestamp=datetime.fromisoformat(ts),
                                type=TransactionType(r.get("type")),
                                category=Category(r.get("category")),
                                amount=amount_val,
                                source_or_merchant=str(r.get("source_or_merchant", "")),
                                receipt_url=str(r.get("receipt_url", "")) or None,
                                notes=str(r.get("notes", "")) or None,
                            )
                        )
                    except Exception as e:
                        logger.warning("Error parsing %s sheet row: %s", ws_name, e)
            except Exception as e:
                logger.warning("Worksheet %s not found: %s", ws_name, e)

        # Sort combined list by timestamp descending (newest first)
        all_txs.sort(key=lambda x: x.timestamp, reverse=True)
        return all_txs[:limit]

    async def get_transactions(
        self,
        user_id: int,
        month_year: Optional[str] = None,
        limit: int = 50,
    ) -> List[Transaction]:
        return await asyncio.to_thread(self._sync_get_transactions, user_id, month_year, limit)

    # --- Monthly Summary ---

    def _sync_get_monthly_summary(self, month_year: str, user_id: int) -> MonthlySummary:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Monthly_Summary")
        records = ws.get_all_records()
        for r in records:
            if str(r.get("month_year")) == month_year and int(r.get("user_id", 0)) == user_id:
                return MonthlySummary(
                    month_year=str(r["month_year"]),
                    user_id=int(r["user_id"]),
                    total_income=_clean_float(r.get("total_income", 0.0)),
                    total_expense=_clean_float(r.get("total_expense", 0.0)),
                    target_salary=_clean_float(r.get("target_salary", settings.DEFAULT_TARGET_SALARY)),
                    actual_salary_drawn=_clean_float(r.get("actual_salary_drawn", 0.0)),
                    buffer_fund_balance=_clean_float(r.get("buffer_fund_balance", 0.0)),
                    emergency_fund=_clean_float(r.get("emergency_fund", 0.0)),
                    investment_total=_clean_float(r.get("investment_total", 0.0)),
                    tax_reserve=_clean_float(r.get("tax_reserve", 0.0)),
                )

        prev_buffer = 0.0
        prev_emergency = 0.0
        prev_investment = 0.0
        prev_tax = 0.0
        for r in records:
            if int(r.get("user_id", 0)) == user_id and str(r.get("month_year", "")) < month_year:
                prev_buffer = max(prev_buffer, _clean_float(r.get("buffer_fund_balance", 0.0)))
                prev_emergency = max(prev_emergency, _clean_float(r.get("emergency_fund", 0.0)))
                prev_investment = max(prev_investment, _clean_float(r.get("investment_total", 0.0)))
                prev_tax = max(prev_tax, _clean_float(r.get("tax_reserve", 0.0)))

        return MonthlySummary(
            month_year=month_year,
            user_id=user_id,
            total_income=0.0,
            total_expense=0.0,
            target_salary=settings.DEFAULT_TARGET_SALARY,
            actual_salary_drawn=0.0,
            buffer_fund_balance=prev_buffer,
            emergency_fund=prev_emergency,
            investment_total=prev_investment,
            tax_reserve=prev_tax,
        )

    async def get_monthly_summary(self, month_year: str, user_id: int) -> MonthlySummary:
        return await asyncio.to_thread(self._sync_get_monthly_summary, month_year, user_id)

    def _sync_save_monthly_summary(self, summary: MonthlySummary) -> None:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Monthly_Summary")
        records = ws.get_all_records()

        row_idx = None
        for i, r in enumerate(records, start=2):
            if str(r.get("month_year")) == summary.month_year and int(r.get("user_id", 0)) == summary.user_id:
                row_idx = i
                break

        row_data = [
            summary.month_year,
            str(summary.user_id),
            float(summary.total_income),
            float(summary.total_expense),
            float(summary.target_salary),
            float(summary.actual_salary_drawn),
            float(summary.buffer_fund_balance),
            float(summary.emergency_fund),
            float(summary.investment_total),
            float(summary.tax_reserve),
        ]

        if row_idx is not None:
            ws.update(range_name=f"A{row_idx}:J{row_idx}", values=[row_data])
        else:
            ws.append_row(row_data)

    async def save_monthly_summary(self, summary: MonthlySummary) -> None:
        await asyncio.to_thread(self._sync_save_monthly_summary, summary)

    # --- User Settings ---

    def _sync_get_user_settings(self, user_id: int) -> UserSettings:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Settings")
        records = ws.get_all_records()
        for r in records:
            if int(r.get("user_id", 0)) == user_id:
                return UserSettings(
                    user_id=int(r["user_id"]),
                    target_salary=_clean_float(r.get("target_salary", settings.DEFAULT_TARGET_SALARY)),
                    tax_percentage=_clean_float(r.get("tax_percentage", settings.DEFAULT_TAX_PERCENTAGE)),
                    needs_budget=_clean_float(r.get("needs_budget", settings.DEFAULT_NEEDS_BUDGET)),
                    wants_budget=_clean_float(r.get("wants_budget", settings.DEFAULT_WANTS_BUDGET)),
                    operational_budget=_clean_float(r.get("operational_budget", settings.DEFAULT_OPERATIONAL_BUDGET)),
                    emergency_target=_clean_float(r.get("emergency_target", settings.DEFAULT_EMERGENCY_TARGET)),
                    currency=str(r.get("currency", settings.DEFAULT_CURRENCY)),
                    freelancer_name=str(r.get("freelancer_name", "Freelance Professional")),
                    payment_details=str(r.get("payment_details", "BCA: 123-456-7890 a/n Freelancer")),
                )

        default_settings = UserSettings(
            user_id=user_id,
            target_salary=settings.DEFAULT_TARGET_SALARY,
            tax_percentage=settings.DEFAULT_TAX_PERCENTAGE,
            needs_budget=settings.DEFAULT_NEEDS_BUDGET,
            wants_budget=settings.DEFAULT_WANTS_BUDGET,
            operational_budget=settings.DEFAULT_OPERATIONAL_BUDGET,
            emergency_target=settings.DEFAULT_EMERGENCY_TARGET,
            currency=settings.DEFAULT_CURRENCY,
        )
        self._sync_update_user_settings(default_settings)
        return default_settings

    async def get_user_settings(self, user_id: int) -> UserSettings:
        return await asyncio.to_thread(self._sync_get_user_settings, user_id)

    def _sync_update_user_settings(self, user_settings: UserSettings) -> None:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Settings")
        records = ws.get_all_records()

        row_idx = None
        for i, r in enumerate(records, start=2):
            if int(r.get("user_id", 0)) == user_settings.user_id:
                row_idx = i
                break

        row_data = [
            str(user_settings.user_id),
            float(user_settings.target_salary),
            float(user_settings.tax_percentage),
            float(user_settings.needs_budget),
            float(user_settings.wants_budget),
            float(user_settings.operational_budget),
            float(user_settings.emergency_target),
            user_settings.currency,
            user_settings.freelancer_name,
            user_settings.payment_details,
        ]

        if row_idx is not None:
            ws.update(range_name=f"A{row_idx}:J{row_idx}", values=[row_data])
        else:
            ws.append_row(row_data)

    async def update_user_settings(self, user_settings: UserSettings) -> None:
        await asyncio.to_thread(self._sync_update_user_settings, user_settings)

    # --- Invoices ---

    def _sync_add_invoice(self, invoice: InvoiceCreate) -> Invoice:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Invoices")
        m_y_num = datetime.now().strftime("%Y%m")
        unique_suffix = str(uuid.uuid4())[:4].upper()
        inv_id = f"INV-{m_y_num}-{unique_suffix}"

        items_json = json.dumps([item.model_dump() for item in invoice.items])
        row = [
            inv_id,
            str(invoice.user_id),
            invoice.client_name,
            invoice.client_email or "",
            invoice.project_title,
            float(invoice.amount),
            invoice.currency,
            invoice.issue_date,
            invoice.due_date,
            invoice.status.value,
            items_json,
            invoice.payment_info or "",
            invoice.notes or "",
            invoice.paid_date or "",
        ]
        ws.append_row(row)
        return Invoice(
            id=inv_id,
            user_id=invoice.user_id,
            client_name=invoice.client_name,
            client_email=invoice.client_email,
            project_title=invoice.project_title,
            amount=invoice.amount,
            currency=invoice.currency,
            issue_date=invoice.issue_date,
            due_date=invoice.due_date,
            status=invoice.status,
            items=invoice.items,
            payment_info=invoice.payment_info,
            notes=invoice.notes,
            paid_date=invoice.paid_date,
        )

    async def add_invoice(self, invoice: InvoiceCreate) -> Invoice:
        return await asyncio.to_thread(self._sync_add_invoice, invoice)

    def _sync_get_invoices(
        self,
        user_id: int,
        status: Optional[InvoiceStatus] = None,
        limit: int = 50,
    ) -> List[Invoice]:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Invoices")
        records = ws.get_all_records()
        results = []
        for r in reversed(records):
            if int(r.get("user_id", 0)) != user_id:
                continue
            r_status = str(r.get("status", ""))
            if status and r_status != status.value:
                continue
            try:
                raw_items = r.get("items_json", "[]")
                items = [InvoiceItem(**item) for item in json.loads(raw_items)] if raw_items else []
                results.append(
                    Invoice(
                        id=str(r["id"]),
                        user_id=int(r["user_id"]),
                        client_name=str(r["client_name"]),
                        client_email=str(r.get("client_email", "")),
                        project_title=str(r["project_title"]),
                        amount=_clean_float(r["amount"]),
                        currency=str(r.get("currency", "IDR")),
                        issue_date=str(r["issue_date"]),
                        due_date=str(r["due_date"]),
                        status=InvoiceStatus(r["status"]),
                        items=items,
                        payment_info=str(r.get("payment_info", "")),
                        notes=str(r.get("notes", "")),
                        paid_date=str(r.get("paid_date", "")) or None,
                    )
                )
            except Exception as e:
                logger.warning("Error parsing invoice sheet row: %s", e)
            if len(results) >= limit:
                break
        return results

    async def get_invoices(
        self,
        user_id: int,
        status: Optional[InvoiceStatus] = None,
        limit: int = 50,
    ) -> List[Invoice]:
        return await asyncio.to_thread(self._sync_get_invoices, user_id, status, limit)

    def _sync_get_invoice_by_id(self, invoice_id: str, user_id: int) -> Optional[Invoice]:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Invoices")
        records = ws.get_all_records()
        for r in records:
            if str(r.get("id")) == invoice_id and int(r.get("user_id", 0)) == user_id:
                raw_items = r.get("items_json", "[]")
                items = [InvoiceItem(**item) for item in json.loads(raw_items)] if raw_items else []
                return Invoice(
                    id=str(r["id"]),
                    user_id=int(r["user_id"]),
                    client_name=str(r["client_name"]),
                    client_email=str(r.get("client_email", "")),
                    project_title=str(r["project_title"]),
                    amount=_clean_float(r["amount"]),
                    currency=str(r.get("currency", "IDR")),
                    issue_date=str(r["issue_date"]),
                    due_date=str(r["due_date"]),
                    status=InvoiceStatus(r["status"]),
                    items=items,
                    payment_info=str(r.get("payment_info", "")),
                    notes=str(r.get("notes", "")),
                    paid_date=str(r.get("paid_date", "")) or None,
                )
        return None

    async def get_invoice_by_id(self, invoice_id: str, user_id: int) -> Optional[Invoice]:
        return await asyncio.to_thread(self._sync_get_invoice_by_id, invoice_id, user_id)

    def _sync_update_invoice_status(
        self,
        invoice_id: str,
        user_id: int,
        status: InvoiceStatus,
        paid_date: Optional[str] = None,
    ) -> bool:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Invoices")
        cell = ws.find(invoice_id)
        if cell:
            row_idx = cell.row
            # Status is Col J (10), paid_date is Col N (14)
            ws.update_cell(row_idx, 10, status.value)
            if paid_date:
                ws.update_cell(row_idx, 14, paid_date)
            return True
        return False

    async def update_invoice_status(
        self,
        invoice_id: str,
        user_id: int,
        status: InvoiceStatus,
        paid_date: Optional[str] = None,
    ) -> bool:
        return await asyncio.to_thread(
            self._sync_update_invoice_status, invoice_id, user_id, status, paid_date
        )

    # --- Goals & Wishlist ---

    def _sync_add_goal(self, goal: FinancialGoalCreate) -> FinancialGoal:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Goals_Wishlist")
        goal_id = str(uuid.uuid4())[:8]
        progress_pct = (goal.current_amount / goal.target_amount * 100.0) if goal.target_amount > 0 else 100.0
        row = [
            goal_id,
            str(goal.user_id),
            goal.name,
            float(goal.target_amount),
            float(goal.current_amount),
            f"{progress_pct:.1f}%",
            float(goal.allocation_percent),
            "TRUE" if goal.is_completed else "FALSE",
            goal.created_at,
            goal.target_date or "",
        ]
        ws.append_row(row)
        return FinancialGoal(
            id=goal_id,
            user_id=goal.user_id,
            name=goal.name,
            target_amount=goal.target_amount,
            current_amount=goal.current_amount,
            allocation_percent=goal.allocation_percent,
            is_completed=goal.is_completed,
            created_at=goal.created_at,
            target_date=goal.target_date,
        )

    async def add_goal(self, goal: FinancialGoalCreate) -> FinancialGoal:
        return await asyncio.to_thread(self._sync_add_goal, goal)

    def _sync_get_goals(self, user_id: int, is_completed: Optional[bool] = None) -> List[FinancialGoal]:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Goals_Wishlist")
        records = ws.get_all_records()
        results = []
        for r in records:
            if int(r.get("user_id", 0)) != user_id:
                continue
            is_comp_val = str(r.get("is_completed", "")).upper() in ["TRUE", "1", "YES"]
            if is_completed is not None and is_comp_val != is_completed:
                continue
            try:
                raw_target = str(r.get("target_amount", 0.0)).replace("Rp", "").replace(".", "").replace(",", "").strip()
                raw_curr = str(r.get("current_amount", 0.0)).replace("Rp", "").replace(".", "").replace(",", "").strip()
                target_amt = float(raw_target) if raw_target else 0.0
                curr_amt = float(raw_curr) if raw_curr else 0.0

                results.append(
                    FinancialGoal(
                        id=str(r["id"]),
                        user_id=int(r["user_id"]),
                        name=str(r["name"]),
                        target_amount=target_amt,
                        current_amount=curr_amt,
                        allocation_percent=float(r.get("allocation_percent", 10.0)),
                        is_completed=is_comp_val,
                        created_at=str(r.get("created_at", "")),
                        target_date=str(r.get("target_date", "")) or None,
                    )
                )
            except Exception as e:
                logger.warning("Error parsing goal row: %s", e)
        results.sort(key=lambda g: g.allocation_percent, reverse=True)
        return results

    async def get_goals(self, user_id: int, is_completed: Optional[bool] = None) -> List[FinancialGoal]:
        return await asyncio.to_thread(self._sync_get_goals, user_id, is_completed)

    def _sync_get_goal_by_id(self, goal_id: str, user_id: int) -> Optional[FinancialGoal]:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Goals_Wishlist")
        records = ws.get_all_records()
        for r in records:
            if str(r.get("id")) == goal_id and int(r.get("user_id", 0)) == user_id:
                raw_target = str(r.get("target_amount", 0.0)).replace("Rp", "").replace(".", "").replace(",", "").strip()
                raw_curr = str(r.get("current_amount", 0.0)).replace("Rp", "").replace(".", "").replace(",", "").strip()
                return FinancialGoal(
                    id=str(r["id"]),
                    user_id=int(r["user_id"]),
                    name=str(r["name"]),
                    target_amount=float(raw_target) if raw_target else 0.0,
                    current_amount=float(raw_curr) if raw_curr else 0.0,
                    allocation_percent=float(r.get("allocation_percent", 10.0)),
                    is_completed=str(r.get("is_completed", "")).upper() in ["TRUE", "1", "YES"],
                    created_at=str(r.get("created_at", "")),
                    target_date=str(r.get("target_date", "")) or None,
                )
        return None

    async def get_goal_by_id(self, goal_id: str, user_id: int) -> Optional[FinancialGoal]:
        return await asyncio.to_thread(self._sync_get_goal_by_id, goal_id, user_id)

    def _sync_update_goal(self, goal: FinancialGoal) -> bool:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Goals_Wishlist")
        cell = ws.find(goal.id)
        if cell:
            row_idx = cell.row
            progress_pct = (goal.current_amount / goal.target_amount * 100.0) if goal.target_amount > 0 else 100.0
            row_data = [
                goal.id,
                str(goal.user_id),
                goal.name,
                float(goal.target_amount),
                float(goal.current_amount),
                f"{progress_pct:.1f}%",
                float(goal.allocation_percent),
                "TRUE" if goal.is_completed else "FALSE",
                goal.created_at,
                goal.target_date or "",
            ]
            ws.update(range_name=f"A{row_idx}:J{row_idx}", values=[row_data])
            return True
        return False

    async def update_goal(self, goal: FinancialGoal) -> bool:
        return await asyncio.to_thread(self._sync_update_goal, goal)

    def _sync_delete_goal(self, goal_id: str, user_id: int) -> bool:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Goals_Wishlist")
        cell = ws.find(goal_id)
        if cell:
            row_vals = ws.row_values(cell.row)
            if len(row_vals) > 1 and int(row_vals[1]) == user_id:
                ws.delete_rows(cell.row)
                return True
        return False

    async def delete_goal(self, goal_id: str, user_id: int) -> bool:
        return await asyncio.to_thread(self._sync_delete_goal, goal_id, user_id)

    # --- Recurring Subscriptions ---

    def _sync_add_subscription(self, sub: SubscriptionCreate) -> Subscription:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Subscriptions")
        sub_id = str(uuid.uuid4())[:8]
        row = [
            sub_id,
            str(sub.user_id),
            sub.name,
            float(sub.amount),
            sub.billing_cycle,
            int(sub.billing_day),
            sub.category.value,
            "TRUE" if sub.is_active else "FALSE",
        ]
        ws.append_row(row)
        return Subscription(
            id=sub_id,
            user_id=sub.user_id,
            name=sub.name,
            amount=sub.amount,
            billing_cycle=sub.billing_cycle,
            billing_day=sub.billing_day,
            category=sub.category,
            is_active=sub.is_active,
        )

    async def add_subscription(self, sub: SubscriptionCreate) -> Subscription:
        return await asyncio.to_thread(self._sync_add_subscription, sub)

    def _sync_get_subscriptions(self, user_id: int, is_active: Optional[bool] = None) -> List[Subscription]:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Subscriptions")
        records = ws.get_all_records()
        results = []
        for r in records:
            if int(r.get("user_id", 0)) != user_id:
                continue
            is_act_val = str(r.get("is_active", "")).upper() in ["TRUE", "1", "YES"]
            if is_active is not None and is_act_val != is_active:
                continue
            try:
                raw_amt = str(r.get("amount", 0.0)).replace("Rp", "").replace(".", "").replace(",", "").strip()
                amount_val = float(raw_amt) if raw_amt else 0.0

                results.append(
                    Subscription(
                        id=str(r["id"]),
                        user_id=int(r["user_id"]),
                        name=str(r["name"]),
                        amount=amount_val,
                        billing_cycle=str(r.get("billing_cycle", "monthly")),
                        billing_day=int(r.get("billing_day", 1)),
                        category=Category(r.get("category", "Operational")),
                        is_active=is_act_val,
                    )
                )
            except Exception as e:
                logger.warning("Error parsing subscription row: %s", e)
        results.sort(key=lambda s: s.billing_day)
        return results

    async def get_subscriptions(self, user_id: int, is_active: Optional[bool] = None) -> List[Subscription]:
        return await asyncio.to_thread(self._sync_get_subscriptions, user_id, is_active)

    def _sync_get_subscription_by_id(self, sub_id: str, user_id: int) -> Optional[Subscription]:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Subscriptions")
        records = ws.get_all_records()
        for r in records:
            if str(r.get("id")) == sub_id and int(r.get("user_id", 0)) == user_id:
                raw_amt = str(r.get("amount", 0.0)).replace("Rp", "").replace(".", "").replace(",", "").strip()
                return Subscription(
                    id=str(r["id"]),
                    user_id=int(r["user_id"]),
                    name=str(r["name"]),
                    amount=float(raw_amt) if raw_amt else 0.0,
                    billing_cycle=str(r.get("billing_cycle", "monthly")),
                    billing_day=int(r.get("billing_day", 1)),
                    category=Category(r.get("category", "Operational")),
                    is_active=str(r.get("is_active", "")).upper() in ["TRUE", "1", "YES"],
                )
        return None

    async def get_subscription_by_id(self, sub_id: str, user_id: int) -> Optional[Subscription]:
        return await asyncio.to_thread(self._sync_get_subscription_by_id, sub_id, user_id)

    def _sync_update_subscription(self, sub: Subscription) -> bool:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Subscriptions")
        cell = ws.find(sub.id)
        if cell:
            row_idx = cell.row
            row_data = [
                sub.id,
                str(sub.user_id),
                sub.name,
                float(sub.amount),
                sub.billing_cycle,
                int(sub.billing_day),
                sub.category.value,
                "TRUE" if sub.is_active else "FALSE",
            ]
            ws.update(range_name=f"A{row_idx}:H{row_idx}", values=[row_data])
            return True
        return False

    async def update_subscription(self, sub: Subscription) -> bool:
        return await asyncio.to_thread(self._sync_update_subscription, sub)

    def _sync_delete_subscription(self, sub_id: str, user_id: int) -> bool:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Subscriptions")
        cell = ws.find(sub_id)
        if cell:
            row_vals = ws.row_values(cell.row)
            if len(row_vals) > 1 and int(row_vals[1]) == user_id:
                ws.delete_rows(cell.row)
                return True
        return False

    async def delete_subscription(self, sub_id: str, user_id: int) -> bool:
        return await asyncio.to_thread(self._sync_delete_subscription, sub_id, user_id)

    # --- Quotations & SPH Methods ---

    def _sync_add_quotation(self, q: QuotationCreate) -> Quotation:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Quotations")
        now_str = datetime.now().strftime("%y%m%d")
        rand_suffix = str(uuid.uuid4())[:4].upper()
        q_id = f"SPH-{now_str}-{rand_suffix}"
        items_json = json.dumps([item.model_dump() for item in q.items])

        row_data = [
            q_id,
            str(q.user_id),
            q.client_name,
            q.client_email or "",
            q.project_title,
            float(q.amount),
            q.currency,
            q.issue_date,
            q.valid_until,
            q.timeline,
            q.revision_limit,
            q.dp_terms,
            q.status.value,
            items_json,
            q.notes or "",
            q.converted_invoice_id or "",
        ]
        ws.append_row(row_data)

        return Quotation(
            id=q_id,
            user_id=q.user_id,
            client_name=q.client_name,
            client_email=q.client_email,
            project_title=q.project_title,
            amount=q.amount,
            currency=q.currency,
            issue_date=q.issue_date,
            valid_until=q.valid_until,
            timeline=q.timeline,
            revision_limit=q.revision_limit,
            dp_terms=q.dp_terms,
            status=q.status,
            items=q.items,
            notes=q.notes,
            converted_invoice_id=q.converted_invoice_id,
        )

    async def add_quotation(self, quotation: QuotationCreate) -> Quotation:
        return await asyncio.to_thread(self._sync_add_quotation, quotation)

    def _sync_get_quotations(
        self,
        user_id: int,
        status: Optional[QuotationStatus] = None,
        limit: int = 50,
    ) -> List[Quotation]:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Quotations")
        records = ws.get_all_records()
        results = []
        for r in reversed(records):
            if int(r.get("user_id", 0)) != user_id:
                continue
            r_status = str(r.get("status", ""))
            if status and r_status != status.value:
                continue
            try:
                raw_items = r.get("items_json", "[]")
                items = [QuotationItem(**item) for item in json.loads(raw_items)] if raw_items else []
                results.append(
                    Quotation(
                        id=str(r["id"]),
                        user_id=int(r["user_id"]),
                        client_name=str(r["client_name"]),
                        client_email=str(r.get("client_email", "")),
                        project_title=str(r["project_title"]),
                        amount=_clean_float(r.get("amount", 0.0)),
                        currency=str(r.get("currency", "IDR")),
                        issue_date=str(r.get("issue_date", "")),
                        valid_until=str(r.get("valid_until", "")),
                        timeline=str(r.get("timeline", "14 Hari Kerja")),
                        revision_limit=str(r.get("revision_limit", "Maksimal 2x Revisi Minor")),
                        dp_terms=str(r.get("dp_terms", "Down Payment 50%")),
                        status=QuotationStatus(r.get("status", "SENT")),
                        items=items,
                        notes=str(r.get("notes", "")),
                        converted_invoice_id=str(r.get("converted_invoice_id", "")) or None,
                    )
                )
            except Exception as e:
                logger.warning("Error parsing quotation row: %s", e)
            if len(results) >= limit:
                break
        return results

    async def get_quotations(
        self,
        user_id: int,
        status: Optional[QuotationStatus] = None,
        limit: int = 50,
    ) -> List[Quotation]:
        return await asyncio.to_thread(self._sync_get_quotations, user_id, status, limit)

    def _sync_get_quotation_by_id(self, quotation_id: str, user_id: int) -> Optional[Quotation]:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Quotations")
        records = ws.get_all_records()
        for r in records:
            if str(r.get("id")) == quotation_id and int(r.get("user_id", 0)) == user_id:
                raw_items = r.get("items_json", "[]")
                items = [QuotationItem(**item) for item in json.loads(raw_items)] if raw_items else []
                return Quotation(
                    id=str(r["id"]),
                    user_id=int(r["user_id"]),
                    client_name=str(r["client_name"]),
                    client_email=str(r.get("client_email", "")),
                    project_title=str(r["project_title"]),
                    amount=_clean_float(r.get("amount", 0.0)),
                    currency=str(r.get("currency", "IDR")),
                    issue_date=str(r.get("issue_date", "")),
                    valid_until=str(r.get("valid_until", "")),
                    timeline=str(r.get("timeline", "14 Hari Kerja")),
                    revision_limit=str(r.get("revision_limit", "Maksimal 2x Revisi Minor")),
                    dp_terms=str(r.get("dp_terms", "Down Payment 50%")),
                    status=QuotationStatus(r.get("status", "SENT")),
                    items=items,
                    notes=str(r.get("notes", "")),
                    converted_invoice_id=str(r.get("converted_invoice_id", "")) or None,
                )
        return None

    async def get_quotation_by_id(self, quotation_id: str, user_id: int) -> Optional[Quotation]:
        return await asyncio.to_thread(self._sync_get_quotation_by_id, quotation_id, user_id)

    def _sync_update_quotation_status(
        self,
        quotation_id: str,
        user_id: int,
        status: QuotationStatus,
        converted_invoice_id: Optional[str] = None,
    ) -> bool:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Quotations")
        cell = ws.find(quotation_id)
        if cell:
            row_idx = cell.row
            ws.update_cell(row_idx, 13, status.value)
            if converted_invoice_id:
                ws.update_cell(row_idx, 16, converted_invoice_id)
            return True
        return False

    async def update_quotation_status(
        self,
        quotation_id: str,
        user_id: int,
        status: QuotationStatus,
        converted_invoice_id: Optional[str] = None,
    ) -> bool:
        return await asyncio.to_thread(self._sync_update_quotation_status, quotation_id, user_id, status, converted_invoice_id)

    def _sync_delete_quotation(self, quotation_id: str, user_id: int) -> bool:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Quotations")
        cell = ws.find(quotation_id)
        if cell:
            row_vals = ws.row_values(cell.row)
            if len(row_vals) > 1 and int(row_vals[1]) == user_id:
                ws.delete_rows(cell.row)
                return True
        return False

    async def delete_quotation(self, quotation_id: str, user_id: int) -> bool:
        return await asyncio.to_thread(self._sync_delete_quotation, quotation_id, user_id)

    # --- Project Termins & Milestones Methods ---

    def _sync_add_termin(self, termin: ProjectTerminCreate) -> ProjectTermin:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Termins_Milestones")
        now_str = datetime.now().strftime("%y%m%d")
        rand_suffix = str(uuid.uuid4())[:4].upper()
        t_id = f"PRJ-{now_str}-{rand_suffix}"
        milestones_json = json.dumps([m.model_dump() for m in termin.milestones])

        row_data = [
            t_id,
            str(termin.user_id),
            termin.client_name,
            termin.project_title,
            float(termin.total_amount),
            termin.currency,
            milestones_json,
            termin.created_at,
            "TRUE" if termin.is_completed else "FALSE",
        ]
        ws.append_row(row_data)

        return ProjectTermin(
            id=t_id,
            user_id=termin.user_id,
            client_name=termin.client_name,
            project_title=termin.project_title,
            total_amount=termin.total_amount,
            currency=termin.currency,
            milestones=termin.milestones,
            created_at=termin.created_at,
            is_completed=termin.is_completed,
        )

    async def add_termin(self, termin: ProjectTerminCreate) -> ProjectTermin:
        return await asyncio.to_thread(self._sync_add_termin, termin)

    def _sync_get_termins(
        self,
        user_id: int,
        is_completed: Optional[bool] = None,
        limit: int = 50,
    ) -> List[ProjectTermin]:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Termins_Milestones")
        records = ws.get_all_records()
        results = []
        for r in reversed(records):
            if int(r.get("user_id", 0)) != user_id:
                continue
            is_comp = str(r.get("is_completed", "")).upper() in ["TRUE", "1", "YES"]
            if is_completed is not None and is_comp != is_completed:
                continue
            try:
                raw_m = r.get("milestones_json", "[]")
                milestones = [ProjectMilestone(**m) for m in json.loads(raw_m)] if raw_m else []
                results.append(
                    ProjectTermin(
                        id=str(r["id"]),
                        user_id=int(r["user_id"]),
                        client_name=str(r["client_name"]),
                        project_title=str(r["project_title"]),
                        total_amount=_clean_float(r.get("total_amount", 0.0)),
                        currency=str(r.get("currency", "IDR")),
                        milestones=milestones,
                        created_at=str(r.get("created_at", "")),
                        is_completed=is_comp,
                    )
                )
            except Exception as e:
                logger.warning("Error parsing termin row: %s", e)
            if len(results) >= limit:
                break
        return results

    async def get_termins(
        self,
        user_id: int,
        is_completed: Optional[bool] = None,
        limit: int = 50,
    ) -> List[ProjectTermin]:
        return await asyncio.to_thread(self._sync_get_termins, user_id, is_completed, limit)

    def _sync_get_termin_by_id(self, termin_id: str, user_id: int) -> Optional[ProjectTermin]:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Termins_Milestones")
        records = ws.get_all_records()
        for r in records:
            if str(r.get("id")) == termin_id and int(r.get("user_id", 0)) == user_id:
                raw_m = r.get("milestones_json", "[]")
                milestones = [ProjectMilestone(**m) for m in json.loads(raw_m)] if raw_m else []
                return ProjectTermin(
                    id=str(r["id"]),
                    user_id=int(r["user_id"]),
                    client_name=str(r["client_name"]),
                    project_title=str(r["project_title"]),
                    total_amount=_clean_float(r.get("total_amount", 0.0)),
                    currency=str(r.get("currency", "IDR")),
                    milestones=milestones,
                    created_at=str(r.get("created_at", "")),
                    is_completed=str(r.get("is_completed", "")).upper() in ["TRUE", "1", "YES"],
                )
        return None

    async def get_termin_by_id(self, termin_id: str, user_id: int) -> Optional[ProjectTermin]:
        return await asyncio.to_thread(self._sync_get_termin_by_id, termin_id, user_id)

    def _sync_update_termin(self, termin: ProjectTermin) -> bool:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Termins_Milestones")
        cell = ws.find(termin.id)
        if cell:
            row_idx = cell.row
            milestones_json = json.dumps([m.model_dump() for m in termin.milestones])
            row_data = [
                termin.id,
                str(termin.user_id),
                termin.client_name,
                termin.project_title,
                float(termin.total_amount),
                termin.currency,
                milestones_json,
                termin.created_at,
                "TRUE" if termin.is_completed else "FALSE",
            ]
            ws.update(range_name=f"A{row_idx}:I{row_idx}", values=[row_data])
            return True
        return False

    async def update_termin(self, termin: ProjectTermin) -> bool:
        return await asyncio.to_thread(self._sync_update_termin, termin)

    def _sync_delete_termin(self, termin_id: str, user_id: int) -> bool:
        sh = self._get_spreadsheet()
        ws = sh.worksheet("Termins_Milestones")
        cell = ws.find(termin_id)
        if cell:
            row_vals = ws.row_values(cell.row)
            if len(row_vals) > 1 and int(row_vals[1]) == user_id:
                ws.delete_rows(cell.row)
                return True
        return False

    async def delete_termin(self, termin_id: str, user_id: int) -> bool:
        return await asyncio.to_thread(self._sync_delete_termin, termin_id, user_id)

