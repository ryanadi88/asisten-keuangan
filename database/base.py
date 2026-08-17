"""
Abstract Base Class for storage backends (SQLite and Google Sheets).
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from database.models import (
    Transaction,
    TransactionCreate,
    MonthlySummary,
    UserSettings,
    Invoice,
    InvoiceCreate,
    InvoiceStatus,
    FinancialGoal,
    FinancialGoalCreate,
    Subscription,
    SubscriptionCreate,
    Quotation,
    QuotationCreate,
    QuotationStatus,
    ProjectTermin,
    ProjectTerminCreate,
)


class StorageBackend(ABC):
    """Abstract interface for database operations."""

    @abstractmethod
    async def init_db(self) -> None:
        """Initialize database tables or Google Sheets worksheets."""
        pass

    @abstractmethod
    async def add_transaction(self, tx: TransactionCreate) -> Transaction:
        """Add a new transaction and return the persisted record."""
        pass

    @abstractmethod
    async def get_transaction_by_id(self, tx_id: str, user_id: int) -> Optional[Transaction]:
        """Fetch a specific transaction by ID."""
        pass

    @abstractmethod
    async def delete_transaction(self, tx_id: str, user_id: int) -> bool:
        """Delete a transaction by ID."""
        pass

    @abstractmethod
    async def get_transactions(
        self,
        user_id: int,
        month_year: Optional[str] = None,
        limit: int = 50,
    ) -> List[Transaction]:
        """Fetch transactions for a specific user and optional month (YYYY-MM)."""
        pass

    @abstractmethod
    async def get_monthly_summary(self, month_year: str, user_id: int) -> MonthlySummary:
        """Retrieve or calculate monthly summary state for a given month and user."""
        pass

    @abstractmethod
    async def save_monthly_summary(self, summary: MonthlySummary) -> None:
        """Persist or update monthly summary state."""
        pass

    @abstractmethod
    async def get_user_settings(self, user_id: int) -> UserSettings:
        """Retrieve user configuration/settings, or default if not set."""
        pass

    @abstractmethod
    async def update_user_settings(self, settings: UserSettings) -> None:
        """Update or create user settings."""
        pass

    @abstractmethod
    async def add_invoice(self, invoice: InvoiceCreate) -> Invoice:
        """Add a new client invoice."""
        pass

    @abstractmethod
    async def get_invoices(
        self,
        user_id: int,
        status: Optional[InvoiceStatus] = None,
        limit: int = 50,
    ) -> List[Invoice]:
        """Fetch invoices for a user, optionally filtered by status."""
        pass

    @abstractmethod
    async def get_invoice_by_id(self, invoice_id: str, user_id: int) -> Optional[Invoice]:
        """Fetch a single invoice by its ID."""
        pass

    @abstractmethod
    async def update_invoice_status(
        self,
        invoice_id: str,
        user_id: int,
        status: InvoiceStatus,
        paid_date: Optional[str] = None,
    ) -> bool:
        """Update invoice payment status."""
        pass

    # --- Goals & Wishlist ---

    @abstractmethod
    async def add_goal(self, goal: FinancialGoalCreate) -> FinancialGoal:
        """Add a new financial wishlist goal."""
        pass

    @abstractmethod
    async def get_goals(self, user_id: int, is_completed: Optional[bool] = None) -> List[FinancialGoal]:
        """Fetch goals for a user."""
        pass

    @abstractmethod
    async def get_goal_by_id(self, goal_id: str, user_id: int) -> Optional[FinancialGoal]:
        """Fetch goal by ID."""
        pass

    @abstractmethod
    async def update_goal(self, goal: FinancialGoal) -> bool:
        """Update goal progress or attributes."""
        pass

    @abstractmethod
    async def delete_goal(self, goal_id: str, user_id: int) -> bool:
        """Delete goal by ID."""
        pass

    # --- Recurring Subscriptions ---

    @abstractmethod
    async def add_subscription(self, sub: SubscriptionCreate) -> Subscription:
        """Add a recurring subscription."""
        pass

    @abstractmethod
    async def get_subscriptions(self, user_id: int, is_active: Optional[bool] = None) -> List[Subscription]:
        """Fetch subscriptions for a user."""
        pass

    @abstractmethod
    async def get_subscription_by_id(self, sub_id: str, user_id: int) -> Optional[Subscription]:
        """Fetch subscription by ID."""
        pass

    @abstractmethod
    async def update_subscription(self, sub: Subscription) -> bool:
        """Update subscription."""
        pass

    @abstractmethod
    async def delete_subscription(self, sub_id: str, user_id: int) -> bool:
        """Delete subscription by ID."""
        pass

    # --- Quotations & SPH ---

    @abstractmethod
    async def add_quotation(self, quotation: QuotationCreate) -> Quotation:
        """Add a new quotation proposal."""
        pass

    @abstractmethod
    async def get_quotations(self, user_id: int, status: Optional[QuotationStatus] = None, limit: int = 50) -> List[Quotation]:
        """Fetch quotations for a user."""
        pass

    @abstractmethod
    async def get_quotation_by_id(self, quotation_id: str, user_id: int) -> Optional[Quotation]:
        """Fetch quotation by ID."""
        pass

    @abstractmethod
    async def update_quotation_status(self, quotation_id: str, user_id: int, status: QuotationStatus, converted_invoice_id: Optional[str] = None) -> bool:
        """Update quotation status."""
        pass

    @abstractmethod
    async def delete_quotation(self, quotation_id: str, user_id: int) -> bool:
        """Delete quotation by ID."""
        pass

    # --- Project Termins & Milestones ---

    @abstractmethod
    async def add_termin(self, termin: ProjectTerminCreate) -> ProjectTermin:
        """Add a new project termin tracker."""
        pass

    @abstractmethod
    async def get_termins(self, user_id: int, is_completed: Optional[bool] = None, limit: int = 50) -> List[ProjectTermin]:
        """Fetch project termins for a user."""
        pass

    @abstractmethod
    async def get_termin_by_id(self, termin_id: str, user_id: int) -> Optional[ProjectTermin]:
        """Fetch project termin by ID."""
        pass

    @abstractmethod
    async def update_termin(self, termin: ProjectTermin) -> bool:
        """Update project termin milestones or state."""
        pass

    @abstractmethod
    async def delete_termin(self, termin_id: str, user_id: int) -> bool:
        """Delete project termin by ID."""
        pass

