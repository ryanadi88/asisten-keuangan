"""
Configuration module for Freelance AI Financial Engine.
Loads environment variables, validates settings, and provides helper utilities.
"""

from pathlib import Path
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = Field(default="", description="Telegram Bot Father token")
    ALLOWED_TELEGRAM_USER_IDS: str = Field(
        default="",
        description="Comma-separated Telegram user IDs allowed to use the bot. Empty allows all.",
    )

    # OpenAI (Optional)
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API Key")
    OPENAI_MODEL: str = Field(default="gpt-4o-mini", description="OpenAI Model for OCR & NLP")

    # Google Gemini AI (Free Tier for Vision OCR, Audio & NLP)
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API Key (Free Tier from Google AI Studio)")
    GEMINI_MODEL: str = Field(default="gemini-3-flash-preview", description="Gemini model name")

    # Database
    DB_BACKEND: str = Field(default="sqlite", description="'sqlite' or 'gsheets'")
    SQLITE_DB_PATH: str = Field(default="data/freelance_finance.db", description="Path to SQLite DB")
    
    # Google Sheets
    GOOGLE_SHEETS_CREDENTIALS_FILE: str = Field(
        default="credentials.json",
        description="Path to Google Service Account JSON file",
    )
    GOOGLE_SPREADSHEET_KEY: str = Field(
        default="Freelance AI Financial Engine",
        description="Google Sheets spreadsheet title or key",
    )

    # Financial Defaults
    DEFAULT_CURRENCY: str = Field(default="IDR", description="Currency symbol/code: IDR, USD, etc.")
    DEFAULT_TAX_PERCENTAGE: float = Field(
        default=10.0,
        description="Default percentage reserved for tax/operational buffer on income",
    )
    DEFAULT_TARGET_SALARY: float = Field(
        default=10_000_000.0,
        description="Target monthly living salary drawn from freelance income",
    )
    DEFAULT_NEEDS_BUDGET: float = Field(
        default=5_000_000.0,
        description="Default monthly budget limit for Needs",
    )
    DEFAULT_WANTS_BUDGET: float = Field(
        default=2_500_000.0,
        description="Default monthly budget limit for Wants",
    )
    DEFAULT_OPERATIONAL_BUDGET: float = Field(
        default=1_500_000.0,
        description="Default monthly budget limit for Operational / Freelance tools",
    )
    DEFAULT_EMERGENCY_TARGET: float = Field(
        default=30_000_000.0,
        description="Target emergency fund balance",
    )

    # Automated Reporting
    REPORT_TIME_HOUR: int = Field(default=20, description="Hour (0-23) for automated report")
    REPORT_TIME_MINUTE: int = Field(default=0, description="Minute (0-59) for automated report")

    # Daily Evening Check-In
    DAILY_CHECKIN_HOUR: int = Field(default=21, description="Hour (0-23) for daily evening reminder")
    DAILY_CHECKIN_MINUTE: int = Field(default=0, description="Minute (0-59) for daily evening reminder")

    @property
    def allowed_users(self) -> List[int]:
        """Parse comma-separated user IDs into a list of integers."""
        if not self.ALLOWED_TELEGRAM_USER_IDS.strip():
            return []
        ids = []
        for raw in self.ALLOWED_TELEGRAM_USER_IDS.split(","):
            raw_clean = raw.strip()
            if raw_clean.isdigit():
                ids.append(int(raw_clean))
        return ids

    def is_user_allowed(self, user_id: int) -> bool:
        """Check if user is authorized to use the bot."""
        allowed = self.allowed_users
        return len(allowed) == 0 or user_id in allowed


# Singleton instance
settings = Settings()


def format_currency(amount: float, currency: Optional[str] = None) -> str:
    """Format numeric amounts nicely with currency symbols and digit separators."""
    curr = currency or settings.DEFAULT_CURRENCY
    curr_upper = curr.upper()

    if curr_upper in ["IDR", "RP"]:
        # Indonesian Rupiah: Rp10.000.000 (no decimals)
        formatted = f"{amount:,.0f}".replace(",", ".")
        return f"Rp{formatted}"
    elif curr_upper in ["USD", "$"]:
        return f"${amount:,.2f}"
    elif curr_upper in ["EUR", "€"]:
        return f"€{amount:,.2f}"
    elif curr_upper in ["GBP", "£"]:
        return f"£{amount:,.2f}"
    elif curr_upper in ["SGD", "S$"]:
        return f"S${amount:,.2f}"
    elif curr_upper in ["MYR", "RM"]:
        return f"RM{amount:,.2f}"
    else:
        return f"{curr_upper} {amount:,.2f}"


def get_current_month_year() -> str:
    """Return current month-year string in format 'YYYY-MM'."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m")
