"""
SQLite storage backend implementation using aiosqlite.
Zero-configuration, production-ready local/embedded database.
"""

import os
import uuid
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional

import aiosqlite

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


class SQLiteBackend(StorageBackend):
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.SQLITE_DB_PATH
        # Ensure parent directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self):
        return aiosqlite.connect(self.db_path)

    async def init_db(self) -> None:
        """Create necessary tables if they do not exist."""
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")

            # 1. Transactions Table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS transactions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount REAL NOT NULL,
                    source_or_merchant TEXT NOT NULL,
                    receipt_url TEXT,
                    notes TEXT
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_tx_user_time ON transactions(user_id, timestamp)"
            )

            # 2. Monthly Summary / Budget State Table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS monthly_summary (
                    month_year TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    total_income REAL NOT NULL DEFAULT 0.0,
                    total_expense REAL NOT NULL DEFAULT 0.0,
                    target_salary REAL NOT NULL DEFAULT 10000000.0,
                    actual_salary_drawn REAL NOT NULL DEFAULT 0.0,
                    buffer_fund_balance REAL NOT NULL DEFAULT 0.0,
                    emergency_fund REAL NOT NULL DEFAULT 0.0,
                    investment_total REAL NOT NULL DEFAULT 0.0,
                    tax_reserve REAL NOT NULL DEFAULT 0.0,
                    PRIMARY KEY (month_year, user_id)
                )
                """
            )

            # 3. User Settings Table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    target_salary REAL NOT NULL,
                    tax_percentage REAL NOT NULL,
                    needs_budget REAL NOT NULL,
                    wants_budget REAL NOT NULL,
                    operational_budget REAL NOT NULL,
                    emergency_target REAL NOT NULL,
                    currency TEXT NOT NULL,
                    freelancer_name TEXT DEFAULT 'Freelance Professional',
                    payment_details TEXT DEFAULT 'BCA: 123-456-7890 a/n Freelancer'
                )
                """
            )

            # 4. Invoices / Client Piutang Table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS invoices (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    client_name TEXT NOT NULL,
                    client_email TEXT,
                    project_title TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    issue_date TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    items_json TEXT,
                    payment_info TEXT,
                    notes TEXT,
                    paid_date TEXT
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_inv_user_status ON invoices(user_id, status)"
            )

            # 5. Financial Goals & Wishlist Table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    target_amount REAL NOT NULL,
                    current_amount REAL NOT NULL DEFAULT 0.0,
                    allocation_percent REAL NOT NULL DEFAULT 10.0,
                    is_completed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    target_date TEXT
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_goals_user ON goals(user_id, is_completed)"
            )

            # 6. Recurring Subscriptions Table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    amount REAL NOT NULL,
                    billing_cycle TEXT NOT NULL DEFAULT 'monthly',
                    billing_day INTEGER NOT NULL DEFAULT 1,
                    category TEXT NOT NULL DEFAULT 'Operational',
                    is_active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_subs_user ON subscriptions(user_id, is_active)"
            )

            # 7. Quotations / Surat Penawaran Harga Table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS quotations (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    client_name TEXT NOT NULL,
                    client_email TEXT,
                    project_title TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'IDR',
                    issue_date TEXT NOT NULL,
                    valid_until TEXT NOT NULL,
                    timeline TEXT NOT NULL,
                    revision_limit TEXT NOT NULL,
                    dp_terms TEXT NOT NULL,
                    status TEXT NOT NULL,
                    items_json TEXT,
                    notes TEXT,
                    converted_invoice_id TEXT
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_quote_user ON quotations(user_id, status)"
            )

            # 8. Project Termins & Milestones Table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS termins (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    client_name TEXT NOT NULL,
                    project_title TEXT NOT NULL,
                    total_amount REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'IDR',
                    milestones_json TEXT,
                    created_at TEXT NOT NULL,
                    is_completed INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_termin_user ON termins(user_id, is_completed)"
            )

            await db.commit()
            logger.info("SQLite database initialized at: %s", self.db_path)

    # --- Transaction Methods ---

    async def add_transaction(self, tx: TransactionCreate) -> Transaction:
        tx_id = str(uuid.uuid4())[:8]
        timestamp_str = tx.timestamp.isoformat()

        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO transactions (
                    id, user_id, timestamp, type, category, amount, source_or_merchant, receipt_url, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tx_id,
                    tx.user_id,
                    timestamp_str,
                    tx.type.value,
                    tx.category.value,
                    float(tx.amount),
                    tx.source_or_merchant,
                    tx.receipt_url,
                    tx.notes or "",
                ),
            )
            await db.commit()

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

    async def get_transaction_by_id(self, tx_id: str, user_id: int) -> Optional[Transaction]:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
                (tx_id, user_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return Transaction(
                id=row["id"],
                user_id=row["user_id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                type=TransactionType(row["type"]),
                category=Category(row["category"]),
                amount=float(row["amount"]),
                source_or_merchant=row["source_or_merchant"],
                receipt_url=row["receipt_url"],
                notes=row["notes"],
            )

    async def delete_transaction(self, tx_id: str, user_id: int) -> bool:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "DELETE FROM transactions WHERE id = ? AND user_id = ?",
                (tx_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_transactions(
        self,
        user_id: int,
        month_year: Optional[str] = None,
        limit: int = 50,
    ) -> List[Transaction]:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            if month_year:
                query = """
                    SELECT * FROM transactions 
                    WHERE user_id = ? AND timestamp LIKE ? 
                    ORDER BY timestamp DESC LIMIT ?
                """
                cursor = await db.execute(query, (user_id, f"{month_year}%", limit))
            else:
                query = """
                    SELECT * FROM transactions 
                    WHERE user_id = ? 
                    ORDER BY timestamp DESC LIMIT ?
                """
                cursor = await db.execute(query, (user_id, limit))

            rows = await cursor.fetchall()
            return [
                Transaction(
                    id=row["id"],
                    user_id=row["user_id"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    type=TransactionType(row["type"]),
                    category=Category(row["category"]),
                    amount=float(row["amount"]),
                    source_or_merchant=row["source_or_merchant"],
                    receipt_url=row["receipt_url"],
                    notes=row["notes"],
                )
                for row in rows
            ]

    # --- Monthly Summary Methods ---

    async def get_monthly_summary(self, month_year: str, user_id: int) -> MonthlySummary:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM monthly_summary WHERE month_year = ? AND user_id = ?",
                (month_year, user_id),
            )
            row = await cursor.fetchone()
            if row:
                return MonthlySummary(
                    month_year=row["month_year"],
                    user_id=row["user_id"],
                    total_income=float(row["total_income"]),
                    total_expense=float(row["total_expense"]),
                    target_salary=float(row["target_salary"]),
                    actual_salary_drawn=float(row["actual_salary_drawn"]),
                    buffer_fund_balance=float(row["buffer_fund_balance"]),
                    emergency_fund=float(row["emergency_fund"]),
                    investment_total=float(row["investment_total"]),
                    tax_reserve=float(row["tax_reserve"]),
                )

            # Inherit previous balances
            cursor_prev = await db.execute(
                """
                SELECT buffer_fund_balance, emergency_fund, investment_total, tax_reserve
                FROM monthly_summary
                WHERE user_id = ? AND month_year < ?
                ORDER BY month_year DESC LIMIT 1
                """,
                (user_id, month_year),
            )
            prev_row = await cursor_prev.fetchone()

            user_settings = await self.get_user_settings(user_id)
            buffer_bal = float(prev_row["buffer_fund_balance"]) if prev_row else 0.0
            emergency_bal = float(prev_row["emergency_fund"]) if prev_row else 0.0
            invest_bal = float(prev_row["investment_total"]) if prev_row else 0.0
            tax_bal = float(prev_row["tax_reserve"]) if prev_row else 0.0

            return MonthlySummary(
                month_year=month_year,
                user_id=user_id,
                total_income=0.0,
                total_expense=0.0,
                target_salary=user_settings.target_salary,
                actual_salary_drawn=0.0,
                buffer_fund_balance=buffer_bal,
                emergency_fund=emergency_bal,
                investment_total=invest_bal,
                tax_reserve=tax_bal,
            )

    async def save_monthly_summary(self, summary: MonthlySummary) -> None:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO monthly_summary (
                    month_year, user_id, total_income, total_expense, target_salary,
                    actual_salary_drawn, buffer_fund_balance, emergency_fund, investment_total, tax_reserve
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(month_year, user_id) DO UPDATE SET
                    total_income = excluded.total_income,
                    total_expense = excluded.total_expense,
                    target_salary = excluded.target_salary,
                    actual_salary_drawn = excluded.actual_salary_drawn,
                    buffer_fund_balance = excluded.buffer_fund_balance,
                    emergency_fund = excluded.emergency_fund,
                    investment_total = excluded.investment_total,
                    tax_reserve = excluded.tax_reserve
                """,
                (
                    summary.month_year,
                    summary.user_id,
                    float(summary.total_income),
                    float(summary.total_expense),
                    float(summary.target_salary),
                    float(summary.actual_salary_drawn),
                    float(summary.buffer_fund_balance),
                    float(summary.emergency_fund),
                    float(summary.investment_total),
                    float(summary.tax_reserve),
                ),
            )
            await db.commit()

    # --- User Settings Methods ---

    async def get_user_settings(self, user_id: int) -> UserSettings:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM user_settings WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            if row:
                # Handle possible column presence safely
                freelancer_name = row["freelancer_name"] if "freelancer_name" in row.keys() else "Freelance Professional"
                payment_details = row["payment_details"] if "payment_details" in row.keys() else "BCA: 123-456-7890 a/n Freelancer"
                return UserSettings(
                    user_id=row["user_id"],
                    target_salary=float(row["target_salary"]),
                    tax_percentage=float(row["tax_percentage"]),
                    needs_budget=float(row["needs_budget"]),
                    wants_budget=float(row["wants_budget"]),
                    operational_budget=float(row["operational_budget"]),
                    emergency_target=float(row["emergency_target"]),
                    currency=row["currency"],
                    freelancer_name=freelancer_name,
                    payment_details=payment_details,
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
                freelancer_name="Freelance Professional",
                payment_details="BCA: 123-456-7890 a/n Freelancer",
            )
            await self.update_user_settings(default_settings)
            return default_settings

    async def update_user_settings(self, user_settings: UserSettings) -> None:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO user_settings (
                    user_id, target_salary, tax_percentage, needs_budget,
                    wants_budget, operational_budget, emergency_target, currency,
                    freelancer_name, payment_details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    target_salary = excluded.target_salary,
                    tax_percentage = excluded.tax_percentage,
                    needs_budget = excluded.needs_budget,
                    wants_budget = excluded.wants_budget,
                    operational_budget = excluded.operational_budget,
                    emergency_target = excluded.emergency_target,
                    currency = excluded.currency,
                    freelancer_name = excluded.freelancer_name,
                    payment_details = excluded.payment_details
                """,
                (
                    user_settings.user_id,
                    float(user_settings.target_salary),
                    float(user_settings.tax_percentage),
                    float(user_settings.needs_budget),
                    float(user_settings.wants_budget),
                    float(user_settings.operational_budget),
                    float(user_settings.emergency_target),
                    user_settings.currency,
                    user_settings.freelancer_name,
                    user_settings.payment_details,
                ),
            )
            await db.commit()

    # --- Invoice / Client Piutang Methods ---

    async def add_invoice(self, invoice: InvoiceCreate) -> Invoice:
        # Generate clean invoice number e.g. INV-202608-A1B2
        inv_code = str(uuid.uuid4())[:4].upper()
        now_prefix = datetime.now().strftime("%Y%m")
        invoice_id = f"INV-{now_prefix}-{inv_code}"

        items_json = json.dumps([item.model_dump() for item in invoice.items])

        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO invoices (
                    id, user_id, client_name, client_email, project_title, amount,
                    currency, issue_date, due_date, status, items_json, payment_info, notes, paid_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    invoice.user_id,
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
                    invoice.paid_date,
                ),
            )
            await db.commit()

        return Invoice(
            id=invoice_id,
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

    async def get_invoices(
        self,
        user_id: int,
        status: Optional[InvoiceStatus] = None,
        limit: int = 50,
    ) -> List[Invoice]:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            if status:
                query = """
                    SELECT * FROM invoices 
                    WHERE user_id = ? AND status = ? 
                    ORDER BY issue_date DESC LIMIT ?
                """
                cursor = await db.execute(query, (user_id, status.value, limit))
            else:
                query = """
                    SELECT * FROM invoices 
                    WHERE user_id = ? 
                    ORDER BY issue_date DESC LIMIT ?
                """
                cursor = await db.execute(query, (user_id, limit))

            rows = await cursor.fetchall()
            results = []
            for row in rows:
                items_raw = row["items_json"]
                items = [InvoiceItem(**item) for item in json.loads(items_raw)] if items_raw else []
                results.append(
                    Invoice(
                        id=row["id"],
                        user_id=row["user_id"],
                        client_name=row["client_name"],
                        client_email=row["client_email"],
                        project_title=row["project_title"],
                        amount=float(row["amount"]),
                        currency=row["currency"],
                        issue_date=row["issue_date"],
                        due_date=row["due_date"],
                        status=InvoiceStatus(row["status"]),
                        items=items,
                        payment_info=row["payment_info"],
                        notes=row["notes"],
                        paid_date=row["paid_date"],
                    )
                )
            return results

    async def get_invoice_by_id(self, invoice_id: str, user_id: int) -> Optional[Invoice]:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM invoices WHERE (id = ? OR id LIKE ?) AND user_id = ?",
                (invoice_id, f"%{invoice_id}%", user_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            items_raw = row["items_json"]
            items = [InvoiceItem(**item) for item in json.loads(items_raw)] if items_raw else []
            return Invoice(
                id=row["id"],
                user_id=row["user_id"],
                client_name=row["client_name"],
                client_email=row["client_email"],
                project_title=row["project_title"],
                amount=float(row["amount"]),
                currency=row["currency"],
                issue_date=row["issue_date"],
                due_date=row["due_date"],
                status=InvoiceStatus(row["status"]),
                items=items,
                payment_info=row["payment_info"],
                notes=row["notes"],
                paid_date=row["paid_date"],
            )

    async def update_invoice_status(
        self,
        invoice_id: str,
        user_id: int,
        status: InvoiceStatus,
        paid_date: Optional[str] = None,
    ) -> bool:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            p_date = paid_date or (datetime.now().strftime("%Y-%m-%d") if status == InvoiceStatus.PAID else None)
            cursor = await db.execute(
                """
                UPDATE invoices 
                SET status = ?, paid_date = ? 
                WHERE (id = ? OR id LIKE ?) AND user_id = ?
                """,
                (status.value, p_date, invoice_id, f"%{invoice_id}%", user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    # --- Goals & Wishlist Methods ---

    async def add_goal(self, goal: FinancialGoalCreate) -> FinancialGoal:
        goal_id = str(uuid.uuid4())[:8]
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO goals (
                    id, user_id, name, target_amount, current_amount, allocation_percent, is_completed, created_at, target_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    goal_id,
                    goal.user_id,
                    goal.name,
                    goal.target_amount,
                    goal.current_amount,
                    goal.allocation_percent,
                    1 if goal.is_completed else 0,
                    goal.created_at,
                    goal.target_date,
                ),
            )
            await db.commit()
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

    async def get_goals(self, user_id: int, is_completed: Optional[bool] = None) -> List[FinancialGoal]:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            if is_completed is not None:
                cursor = await db.execute(
                    "SELECT * FROM goals WHERE user_id = ? AND is_completed = ? ORDER BY allocation_percent DESC, created_at ASC",
                    (user_id, 1 if is_completed else 0),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM goals WHERE user_id = ? ORDER BY is_completed ASC, allocation_percent DESC",
                    (user_id,),
                )
            rows = await cursor.fetchall()
            return [
                FinancialGoal(
                    id=row["id"],
                    user_id=row["user_id"],
                    name=row["name"],
                    target_amount=float(row["target_amount"]),
                    current_amount=float(row["current_amount"]),
                    allocation_percent=float(row["allocation_percent"]),
                    is_completed=bool(row["is_completed"]),
                    created_at=row["created_at"],
                    target_date=row["target_date"],
                )
                for row in rows
            ]

    async def get_goal_by_id(self, goal_id: str, user_id: int) -> Optional[FinancialGoal]:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM goals WHERE (id = ? OR id LIKE ?) AND user_id = ?",
                (goal_id, f"%{goal_id}%", user_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return FinancialGoal(
                id=row["id"],
                user_id=row["user_id"],
                name=row["name"],
                target_amount=float(row["target_amount"]),
                current_amount=float(row["current_amount"]),
                allocation_percent=float(row["allocation_percent"]),
                is_completed=bool(row["is_completed"]),
                created_at=row["created_at"],
                target_date=row["target_date"],
            )

    async def update_goal(self, goal: FinancialGoal) -> bool:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                UPDATE goals
                SET name = ?, target_amount = ?, current_amount = ?, allocation_percent = ?, is_completed = ?, target_date = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    goal.name,
                    goal.target_amount,
                    goal.current_amount,
                    goal.allocation_percent,
                    1 if goal.is_completed else 0,
                    goal.target_date,
                    goal.id,
                    goal.user_id,
                ),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_goal(self, goal_id: str, user_id: int) -> bool:
        async with self._get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM goals WHERE (id = ? OR id LIKE ?) AND user_id = ?",
                (goal_id, f"%{goal_id}%", user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    # --- Subscriptions Methods ---

    async def add_subscription(self, sub: SubscriptionCreate) -> Subscription:
        sub_id = str(uuid.uuid4())[:8]
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO subscriptions (
                    id, user_id, name, amount, billing_cycle, billing_day, category, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sub_id,
                    sub.user_id,
                    sub.name,
                    sub.amount,
                    sub.billing_cycle,
                    sub.billing_day,
                    sub.category.value,
                    1 if sub.is_active else 0,
                ),
            )
            await db.commit()
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

    async def get_subscriptions(self, user_id: int, is_active: Optional[bool] = None) -> List[Subscription]:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            if is_active is not None:
                cursor = await db.execute(
                    "SELECT * FROM subscriptions WHERE user_id = ? AND is_active = ? ORDER BY billing_day ASC",
                    (user_id, 1 if is_active else 0),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY is_active DESC, billing_day ASC",
                    (user_id,),
                )
            rows = await cursor.fetchall()
            return [
                Subscription(
                    id=row["id"],
                    user_id=row["user_id"],
                    name=row["name"],
                    amount=float(row["amount"]),
                    billing_cycle=row["billing_cycle"],
                    billing_day=int(row["billing_day"]),
                    category=Category(row["category"]),
                    is_active=bool(row["is_active"]),
                )
                for row in rows
            ]

    async def get_subscription_by_id(self, sub_id: str, user_id: int) -> Optional[Subscription]:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM subscriptions WHERE (id = ? OR id LIKE ?) AND user_id = ?",
                (sub_id, f"%{sub_id}%", user_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return Subscription(
                id=row["id"],
                user_id=row["user_id"],
                name=row["name"],
                amount=float(row["amount"]),
                billing_cycle=row["billing_cycle"],
                billing_day=int(row["billing_day"]),
                category=Category(row["category"]),
                is_active=bool(row["is_active"]),
            )

    async def update_subscription(self, sub: Subscription) -> bool:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                UPDATE subscriptions
                SET name = ?, amount = ?, billing_cycle = ?, billing_day = ?, category = ?, is_active = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    sub.name,
                    sub.amount,
                    sub.billing_cycle,
                    sub.billing_day,
                    sub.category.value,
                    1 if sub.is_active else 0,
                    sub.id,
                    sub.user_id,
                ),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_subscription(self, sub_id: str, user_id: int) -> bool:
        async with self._get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM subscriptions WHERE (id = ? OR id LIKE ?) AND user_id = ?",
                (sub_id, f"%{sub_id}%", user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    # --- Quotations & SPH Methods ---

    async def add_quotation(self, q: QuotationCreate) -> Quotation:
        now_str = datetime.now().strftime("%y%m%d")
        rand_suffix = str(uuid.uuid4())[:4].upper()
        q_id = f"SPH-{now_str}-{rand_suffix}"
        items_json = json.dumps([item.model_dump() for item in q.items])

        async with self._get_connection() as db:
            await db.execute(
                """
                INSERT INTO quotations (
                    id, user_id, client_name, client_email, project_title, amount,
                    currency, issue_date, valid_until, timeline, revision_limit,
                    dp_terms, status, items_json, notes, converted_invoice_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    q_id,
                    q.user_id,
                    q.client_name,
                    q.client_email,
                    q.project_title,
                    q.amount,
                    q.currency,
                    q.issue_date,
                    q.valid_until,
                    q.timeline,
                    q.revision_limit,
                    q.dp_terms,
                    q.status.value,
                    items_json,
                    q.notes,
                    q.converted_invoice_id,
                ),
            )
            await db.commit()

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

    async def get_quotations(
        self,
        user_id: int,
        status: Optional[QuotationStatus] = None,
        limit: int = 50,
    ) -> List[Quotation]:
        query = "SELECT * FROM quotations WHERE user_id = ?"
        params = [user_id]
        if status:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY issue_date DESC LIMIT ?"
        params.append(limit)

        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                raw_items = row["items_json"]
                items = [QuotationItem(**item) for item in json.loads(raw_items)] if raw_items else []
                results.append(
                    Quotation(
                        id=row["id"],
                        user_id=row["user_id"],
                        client_name=row["client_name"],
                        client_email=row["client_email"],
                        project_title=row["project_title"],
                        amount=float(row["amount"]),
                        currency=row["currency"],
                        issue_date=row["issue_date"],
                        valid_until=row["valid_until"],
                        timeline=row["timeline"],
                        revision_limit=row["revision_limit"],
                        dp_terms=row["dp_terms"],
                        status=QuotationStatus(row["status"]),
                        items=items,
                        notes=row["notes"],
                        converted_invoice_id=row["converted_invoice_id"],
                    )
                )
            return results

    async def get_quotation_by_id(self, quotation_id: str, user_id: int) -> Optional[Quotation]:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM quotations WHERE (id = ? OR id LIKE ?) AND user_id = ?",
                (quotation_id, f"%{quotation_id}%", user_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            raw_items = row["items_json"]
            items = [QuotationItem(**item) for item in json.loads(raw_items)] if raw_items else []
            return Quotation(
                id=row["id"],
                user_id=row["user_id"],
                client_name=row["client_name"],
                client_email=row["client_email"],
                project_title=row["project_title"],
                amount=float(row["amount"]),
                currency=row["currency"],
                issue_date=row["issue_date"],
                valid_until=row["valid_until"],
                timeline=row["timeline"],
                revision_limit=row["revision_limit"],
                dp_terms=row["dp_terms"],
                status=QuotationStatus(row["status"]),
                items=items,
                notes=row["notes"],
                converted_invoice_id=row["converted_invoice_id"],
            )

    async def update_quotation_status(
        self,
        quotation_id: str,
        user_id: int,
        status: QuotationStatus,
        converted_invoice_id: Optional[str] = None,
    ) -> bool:
        async with self._get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE quotations
                SET status = ?, converted_invoice_id = COALESCE(?, converted_invoice_id)
                WHERE (id = ? OR id LIKE ?) AND user_id = ?
                """,
                (status.value, converted_invoice_id, quotation_id, f"%{quotation_id}%", user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_quotation(self, quotation_id: str, user_id: int) -> bool:
        async with self._get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM quotations WHERE (id = ? OR id LIKE ?) AND user_id = ?",
                (quotation_id, f"%{quotation_id}%", user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    # --- Project Termins & Milestones Methods ---

    async def add_termin(self, termin: ProjectTerminCreate) -> ProjectTermin:
        now_str = datetime.now().strftime("%y%m%d")
        rand_suffix = str(uuid.uuid4())[:4].upper()
        t_id = f"PRJ-{now_str}-{rand_suffix}"
        milestones_json = json.dumps([m.model_dump() for m in termin.milestones])

        async with self._get_connection() as db:
            await db.execute(
                """
                INSERT INTO termins (
                    id, user_id, client_name, project_title, total_amount,
                    currency, milestones_json, created_at, is_completed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    t_id,
                    termin.user_id,
                    termin.client_name,
                    termin.project_title,
                    termin.total_amount,
                    termin.currency,
                    milestones_json,
                    termin.created_at,
                    1 if termin.is_completed else 0,
                ),
            )
            await db.commit()

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

    async def get_termins(
        self,
        user_id: int,
        is_completed: Optional[bool] = None,
        limit: int = 50,
    ) -> List[ProjectTermin]:
        query = "SELECT * FROM termins WHERE user_id = ?"
        params = [user_id]
        if is_completed is not None:
            query += " AND is_completed = ?"
            params.append(1 if is_completed else 0)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                raw_m = row["milestones_json"]
                milestones = [ProjectMilestone(**m) for m in json.loads(raw_m)] if raw_m else []
                results.append(
                    ProjectTermin(
                        id=row["id"],
                        user_id=row["user_id"],
                        client_name=row["client_name"],
                        project_title=row["project_title"],
                        total_amount=float(row["total_amount"]),
                        currency=row["currency"],
                        milestones=milestones,
                        created_at=row["created_at"],
                        is_completed=bool(row["is_completed"]),
                    )
                )
            return results

    async def get_termin_by_id(self, termin_id: str, user_id: int) -> Optional[ProjectTermin]:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM termins WHERE (id = ? OR id LIKE ?) AND user_id = ?",
                (termin_id, f"%{termin_id}%", user_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            raw_m = row["milestones_json"]
            milestones = [ProjectMilestone(**m) for m in json.loads(raw_m)] if raw_m else []
            return ProjectTermin(
                id=row["id"],
                user_id=row["user_id"],
                client_name=row["client_name"],
                project_title=row["project_title"],
                total_amount=float(row["total_amount"]),
                currency=row["currency"],
                milestones=milestones,
                created_at=row["created_at"],
                is_completed=bool(row["is_completed"]),
            )

    async def update_termin(self, termin: ProjectTermin) -> bool:
        milestones_json = json.dumps([m.model_dump() for m in termin.milestones])
        async with self._get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE termins
                SET client_name = ?, project_title = ?, total_amount = ?, currency = ?,
                    milestones_json = ?, is_completed = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    termin.client_name,
                    termin.project_title,
                    termin.total_amount,
                    termin.currency,
                    milestones_json,
                    1 if termin.is_completed else 0,
                    termin.id,
                    termin.user_id,
                ),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_termin(self, termin_id: str, user_id: int) -> bool:
        async with self._get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM termins WHERE (id = ? OR id LIKE ?) AND user_id = ?",
                (termin_id, f"%{termin_id}%", user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

