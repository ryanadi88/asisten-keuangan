"""
Data models, enums, and schemas for Freelance AI Financial Engine.
"""

from datetime import datetime, date
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class TransactionType(str, Enum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class Category(str, Enum):
    NEEDS = "Needs"
    WANTS = "Wants"
    OPERATIONAL = "Operational"
    BUFFER = "Buffer"
    INVESTMENT = "Investment"
    EMERGENCY = "Emergency"


class BudgetGuardStatus(str, Enum):
    OK = "OK"
    WARNING = "WARNING"  # >= 80% and < 100%
    BREACH = "BREACH"    # >= 100%


class InvoiceStatus(str, Enum):
    UNPAID = "UNPAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class InvoiceItem(BaseModel):
    description: str = Field(description="Item or milestone description")
    quantity: float = Field(default=1.0, description="Quantity or hours")
    rate: float = Field(gt=0, description="Unit rate or price")
    amount: float = Field(gt=0, description="Total amount for item")


class TransactionBase(BaseModel):
    user_id: int = Field(default=0, description="Telegram User ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="Transaction timestamp")
    type: TransactionType = Field(description="INCOME or EXPENSE")
    category: Category = Field(description="Needs, Wants, Operational, Buffer, Investment, Emergency")
    amount: float = Field(gt=0, description="Transaction amount in base currency")
    source_or_merchant: str = Field(default="Unknown", description="Client name, store, or vendor")
    receipt_url: Optional[str] = Field(default=None, description="Image URL or local file reference")
    notes: Optional[str] = Field(default="", description="Additional remarks or item descriptions")


class TransactionCreate(TransactionBase):
    pass


class Transaction(TransactionBase):
    id: str = Field(description="Unique UUID or row identifier")
    model_config = ConfigDict(from_attributes=True)


class InvoiceBase(BaseModel):
    user_id: int = Field(description="Telegram user ID")
    client_name: str = Field(description="Client or company name")
    client_email: Optional[str] = Field(default="", description="Client contact email")
    project_title: str = Field(description="Project or scope title")
    amount: float = Field(gt=0, description="Total invoice amount")
    currency: str = Field(default="IDR", description="Currency code (IDR, USD, etc.)")
    issue_date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"), description="Invoice issue date (YYYY-MM-DD)")
    due_date: str = Field(description="Due date for payment (YYYY-MM-DD)")
    status: InvoiceStatus = Field(default=InvoiceStatus.UNPAID, description="Payment status")
    items: List[InvoiceItem] = Field(default_factory=list, description="Line items")
    payment_info: Optional[str] = Field(default="", description="Bank transfer or e-wallet account details")
    notes: Optional[str] = Field(default="", description="Terms or special instructions")
    paid_date: Optional[str] = Field(default=None, description="Date when payment was settled")


class InvoiceCreate(InvoiceBase):
    pass


class Invoice(InvoiceBase):
    id: str = Field(description="Unique invoice number e.g. INV-202608-001")
    model_config = ConfigDict(from_attributes=True)


class PTKPStatus(str, Enum):
    TK0 = "TK/0"  # Tidak Kawin, 0 Tanggungan (Rp 54.000.000)
    TK1 = "TK/1"  # Tidak Kawin, 1 Tanggungan (Rp 58.500.000)
    TK2 = "TK/2"  # Tidak Kawin, 2 Tanggungan (Rp 63.000.000)
    TK3 = "TK/3"  # Tidak Kawin, 3 Tanggungan (Rp 67.500.000)
    K0 = "K/0"    # Kawin, 0 Tanggungan (Rp 58.500.000)
    K1 = "K/1"    # Kawin, 1 Tanggungan (Rp 63.000.000)
    K2 = "K/2"    # Kawin, 2 Tanggungan (Rp 67.500.000)
    K3 = "K/3"    # Kawin, 3 Tanggungan (Rp 72.000.000)


class TaxMethod(str, Enum):
    NPPN_FREELANCE = "NPPN_50%"       # Norma Penghitungan Penghasilan Neto 50%
    PPH_FINAL_UMKM = "PPH_FINAL_0.5%"  # PPh Final PP 55/2022 (0.5% di atas 500jt)


class UserSettings(BaseModel):
    user_id: int = Field(description="Telegram user ID")
    target_salary: float = Field(default=10_000_000.0, description="Monthly minimum living salary target")
    tax_percentage: float = Field(default=10.0, description="Tax / Operational reserve percentage")
    needs_budget: float = Field(default=5_000_000.0, description="Monthly Needs spending limit")
    wants_budget: float = Field(default=2_500_000.0, description="Monthly Wants spending limit")
    operational_budget: float = Field(default=1_500_000.0, description="Monthly Operational budget")
    emergency_target: float = Field(default=30_000_000.0, description="Emergency fund target")
    currency: str = Field(default="IDR", description="Preferred currency")
    freelancer_name: str = Field(default="Freelance Professional", description="Freelancer full name for invoices")
    payment_details: str = Field(default="BCA: 123-456-7890 a/n Freelancer", description="Bank / Payment details for invoices")
    ptkp_status: PTKPStatus = Field(default=PTKPStatus.TK0, description="Status PTKP Pajak")
    nppn_rate: float = Field(default=50.0, description="Persentase Norma NPPN (Default 50% untuk Freelancer)")
    weekly_billable_hours: float = Field(default=30.0, description="Jam kerja produktif per minggu")


class MonthlySummary(BaseModel):
    month_year: str = Field(description="Month and year (e.g. 2026-08)")
    user_id: int = Field(default=0, description="Telegram user ID")
    total_income: float = Field(default=0.0, description="Gross total income received this month")
    total_expense: float = Field(default=0.0, description="Total expenses spent this month")
    target_salary: float = Field(default=10_000_000.0, description="Monthly target living cost")
    actual_salary_drawn: float = Field(default=0.0, description="Salary successfully drawn this month")
    buffer_fund_balance: float = Field(default=0.0, description="Cumulative buffer / smoothing pool")
    emergency_fund: float = Field(default=0.0, description="Emergency fund balance")
    investment_total: float = Field(default=0.0, description="Investment portfolio balance")
    tax_reserve: float = Field(default=0.0, description="Tax & operational reserve balance")

    @property
    def buffer_runway_months(self) -> float:
        """Calculate how many months of target salary are protected in the buffer fund."""
        if self.target_salary <= 0:
            return 0.0
        return round(self.buffer_fund_balance / self.target_salary, 1)

    @property
    def net_savings(self) -> float:
        return self.total_income - self.total_expense


class BudgetCheckResult(BaseModel):
    category: Category
    current_spent: float
    new_amount: float
    total_spent: float
    budget_limit: float
    percentage_used: float
    status: BudgetGuardStatus
    message: str
    remaining_budget: float


class IncomeSplitResult(BaseModel):
    gross_income: float
    tax_reserve_amount: float
    tax_percentage: float
    net_income: float
    salary_drawn_allocated: float
    target_salary: float
    total_salary_drawn_month: float
    salary_target_met: bool
    buffer_pool_allocated: float
    emergency_allocated: float = 0.0
    investment_allocated: float = 0.0
    current_buffer_balance: float
    buffer_runway_months: float
    message: str


class ParsedAIInput(BaseModel):
    type: TransactionType
    category: Category
    amount: float
    source_or_merchant: str
    date: Optional[str] = None
    items: Optional[List[str]] = None
    notes: Optional[str] = None
    confidence: float = 1.0


# --- Goals & Wishlist ---

class FinancialGoalBase(BaseModel):
    user_id: int = Field(description="Telegram user ID")
    name: str = Field(description="Goal name e.g. Macbook M3, Liburan Jepang")
    target_amount: float = Field(gt=0, description="Target savings amount in base currency")
    current_amount: float = Field(default=0.0, ge=0, description="Currently saved amount")
    allocation_percent: float = Field(default=10.0, ge=0, le=100, description="Percentage of incoming income auto-allocated")
    is_completed: bool = Field(default=False, description="Whether goal is 100% achieved")
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"), description="Creation date")
    target_date: Optional[str] = Field(default=None, description="Optional target completion date (YYYY-MM-DD)")


class FinancialGoalCreate(FinancialGoalBase):
    pass


class FinancialGoal(FinancialGoalBase):
    id: str = Field(description="Unique goal ID")
    model_config = ConfigDict(from_attributes=True)

    @property
    def percentage_achieved(self) -> float:
        if self.target_amount <= 0:
            return 100.0
        return min(100.0, round((self.current_amount / self.target_amount) * 100.0, 1))

    @property
    def remaining_amount(self) -> float:
        return max(0.0, self.target_amount - self.current_amount)


class GoalAllocationItem(BaseModel):
    goal_id: str
    goal_name: str
    allocated_amount: float
    new_current_amount: float
    target_amount: float
    percentage_achieved: float
    is_now_completed: bool = False


# --- Recurring Subscriptions & Fixed Bills ---

class SubscriptionBase(BaseModel):
    user_id: int = Field(description="Telegram user ID")
    name: str = Field(description="Service name e.g. ChatGPT Plus, Figma, VPS Hosting")
    amount: float = Field(gt=0, description="Recurring cost per cycle")
    billing_cycle: str = Field(default="monthly", description="'monthly' or 'yearly'")
    billing_day: int = Field(default=1, ge=1, le=31, description="Day of month when bill renews (1-31)")
    category: Category = Field(default=Category.OPERATIONAL, description="Category of the expense")
    is_active: bool = Field(default=True, description="Active status")


class SubscriptionCreate(SubscriptionBase):
    pass


class Subscription(SubscriptionBase):
    id: str = Field(description="Unique subscription ID")
    model_config = ConfigDict(from_attributes=True)


# --- Financial Health Score ---

class FinancialHealthReport(BaseModel):
    score: int = Field(ge=0, le=100, description="Overall health score 0-100")
    grade: str = Field(description="A+, A, B, C, or D")
    grade_label: str = Field(description="e.g. Benteng Finansial Super Kuat")
    runway_months: float
    runway_score: float
    savings_rate_score: float
    discipline_score: float
    tax_discipline_score: float
    recommendations: List[str]
    summary_text: str


# --- Quotations & Surat Penawaran Harga (SPH) ---

class QuotationStatus(str, Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CONVERTED = "CONVERTED"


class QuotationItem(BaseModel):
    description: str = Field(description="Scope item or deliverable description")
    quantity: float = Field(default=1.0, description="Quantity, days, or hours")
    rate: float = Field(gt=0, description="Rate or unit price")
    amount: float = Field(gt=0, description="Total item price")


class QuotationBase(BaseModel):
    user_id: int = Field(description="Telegram user ID")
    client_name: str = Field(description="Client or company name")
    client_email: Optional[str] = Field(default="", description="Client contact email")
    project_title: str = Field(description="Project or proposal title")
    amount: float = Field(gt=0, description="Total quotation estimate amount")
    currency: str = Field(default="IDR", description="Currency code")
    issue_date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"), description="Issue date")
    valid_until: str = Field(description="Proposal validity expiry date (YYYY-MM-DD)")
    timeline: str = Field(default="14 Hari Kerja", description="Estimated work duration")
    revision_limit: str = Field(default="Maksimal 2x Revisi Minor", description="Scope of revisions")
    dp_terms: str = Field(default="Down Payment 50% sebelum mulai pengerjaan", description="Payment terms")
    status: QuotationStatus = Field(default=QuotationStatus.SENT, description="Quotation status")
    items: List[QuotationItem] = Field(default_factory=list, description="Deliverables breakdown")
    notes: Optional[str] = Field(default="", description="Additional terms, scope constraints, and notes")
    converted_invoice_id: Optional[str] = Field(default=None, description="Linked invoice ID if accepted")


class QuotationCreate(QuotationBase):
    pass


class Quotation(QuotationBase):
    id: str = Field(description="Unique quotation number e.g. SPH-202608-001")
    model_config = ConfigDict(from_attributes=True)


# --- Project Termins & Milestones ---

class MilestoneStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    INVOICED = "INVOICED"
    PAID = "PAID"


class ProjectMilestone(BaseModel):
    id: str = Field(description="Milestone ID e.g. m1, m2")
    title: str = Field(description="Milestone description e.g. 'Termin 1 - DP 50%'")
    percentage: float = Field(gt=0, le=100, description="Percentage of project total")
    amount: float = Field(gt=0, description="Nominal amount for this milestone")
    status: MilestoneStatus = Field(default=MilestoneStatus.PENDING, description="Milestone progress status")
    due_date: Optional[str] = Field(default=None, description="Target completion / billing date")
    invoice_id: Optional[str] = Field(default=None, description="Linked invoice ID when invoiced")


class ProjectTerminBase(BaseModel):
    user_id: int = Field(description="Telegram user ID")
    client_name: str = Field(description="Client or company name")
    project_title: str = Field(description="Project title")
    total_amount: float = Field(gt=0, description="Total project contract amount")
    currency: str = Field(default="IDR", description="Currency code")
    milestones: List[ProjectMilestone] = Field(default_factory=list, description="Project milestone phases")
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"), description="Creation date")
    is_completed: bool = Field(default=False, description="Whether all milestones are settled")


class ProjectTerminCreate(ProjectTerminBase):
    pass


class ProjectTermin(ProjectTerminBase):
    id: str = Field(description="Unique termin project ID e.g. PRJ-260817-A1")
    model_config = ConfigDict(from_attributes=True)

    @property
    def total_billed(self) -> float:
        return sum(m.amount for m in self.milestones if m.status in [MilestoneStatus.INVOICED, MilestoneStatus.PAID])

    @property
    def total_paid(self) -> float:
        return sum(m.amount for m in self.milestones if m.status == MilestoneStatus.PAID)

    @property
    def total_unbilled(self) -> float:
        return max(0.0, self.total_amount - self.total_billed)


# --- Instant Affordability Radar ---

class AffordabilityRating(str, Enum):
    GREEN = "GREEN"    # Aman dibeli
    YELLOW = "YELLOW"  # Pikir ulang / Perlu penghematan
    RED = "RED"        # Jangan beli / Bahaya


class AffordabilityReport(BaseModel):
    item_name: str
    price: float
    rating: AffordabilityRating
    verdict_title: str
    verdict_badge: str
    wants_budget_remaining_before: float
    wants_budget_remaining_after: float
    runway_months_before: float
    runway_months_after: float
    daily_safe_spend_before: float
    daily_safe_spend_after: float
    goals_delay_impact: Optional[str] = None
    recommendations: List[str]
    summary_card: str


# --- 90-Day Cashflow Forecasting ---

class CashflowMonthForecast(BaseModel):
    month_name: str                     # e.g. "September 2026"
    month_year: str                     # e.g. "2026-09"
    projected_income: float
    confirmed_invoices_due: float
    fixed_burn_rate: float              # Living needs + subscriptions
    projected_net_cashflow: float
    projected_ending_balance: float
    projected_runway_months: float
    health_status: str                  # "🛡️ Aman", "⚖️ Ketat", "⚠️ Waspada"


class CashflowForecastReport(BaseModel):
    current_buffer_balance: float
    current_monthly_burn: float
    months: List[CashflowMonthForecast]
    optimistic_end_balance: float
    conservative_end_balance: float
    strategic_insights: List[str]
    summary_card: str


# --- Multi-Currency & Forex Exchange ---

class CurrencyExchangeRate(BaseModel):
    base_currency: str = "USD"
    rates: Dict[str, float] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    source: str = "Bank Indonesia / OpenFX"


class CurrencyConversionResult(BaseModel):
    from_currency: str
    to_currency: str
    original_amount: float
    converted_amount: float
    exchange_rate: float
    estimated_platform_fee: float       # e.g. Upwork 10% or PayPal 4.4%
    net_received_idr: float
    timestamp: str
    summary_text: str


# --- AI Tax Estimator & SPT Tahunan Form 1770 ---

class MonthlyRevenueRow(BaseModel):
    month_name: str                     # e.g. "Januari 2026"
    month_year: str                     # e.g. "2026-01"
    gross_income: float                 # Peredaran Bruto
    nppn_rate: float                    # e.g. 50.0%
    net_income: float                   # Penghasilan Neto
    is_projected: bool = False          # True jika bulan masa depan


class TaxBracketDetail(BaseModel):
    bracket_name: str                   # e.g. "Lapisan 1 (5% s.d Rp 60 Juta)"
    taxable_slice: float
    rate_percent: float
    tax_amount: float


class TaxCalculationReport(BaseModel):
    tax_year: int
    tax_method: TaxMethod
    ptkp_status: PTKPStatus
    ptkp_amount: float
    total_annual_gross: float           # Total Peredaran Bruto setahun
    total_annual_net: float             # Total Penghasilan Neto
    pkp_amount: float                   # Penghasilan Kena Pajak (Neto - PTKP)
    brackets: List[TaxBracketDetail]
    total_tax_due: float                # PPh Terutang Setahun
    monthly_tax_installment: float      # PPh Pasal 25 per bulan
    effective_tax_rate: float           # % Pajak Efektif terhadap Omzet
    monthly_breakdown: List[MonthlyRevenueRow]
    summary_card: str
    djp_filling_guide: str


# --- Hourly Rate & Smart Project Pricing ---

class PricingTier(BaseModel):
    tier_name: str                      # "Floor Price", "Recommended", "Value/Premium"
    tier_badge: str                     # "🛡️ Batas Bawah", "🎯 Standar Pasar", "💎 Value-Based Premium"
    total_price: float
    effective_hourly_rate: float
    profit_margin_percent: float
    description: str


class PricingEstimateReport(BaseModel):
    project_title: str
    estimated_hours: float
    complexity_level: str               # "Simple", "Medium", "Complex"
    minimum_hourly_rate: float          # MAR (Minimum Acceptable Rate)
    target_monthly_salary: float
    living_cost_per_hour: float
    tiers: List[PricingTier]
    scope_recommendations: List[str]
    summary_card: str



