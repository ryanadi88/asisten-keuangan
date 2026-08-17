"""
Matplotlib Visual Chart Generator for rich Telegram financial reports.
Generates dark-mode high-aesthetic charts for income vs expense and category allocations.
"""

import io
import logging
from typing import Dict, List, Optional
import matplotlib
# Use Agg backend for non-GUI headless server environments
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from database.models import MonthlySummary, Transaction, TransactionType, Category
from config import format_currency

logger = logging.getLogger(__name__)


def make_ascii_bar(percent: float, length: int = 10) -> str:
    """Generate a clean ASCII progress bar e.g. [████████░░]."""
    clamped_pct = max(0.0, min(100.0, percent))
    filled_len = int(round(length * clamped_pct / 100))
    bar = "█" * filled_len + "░" * (length - filled_len)
    return f"[{bar}] {percent:.0f}%"


class ChartGenerator:
    """Generates modern dark-mode financial charts."""

    @staticmethod
    def generate_monthly_chart(
        summary: MonthlySummary,
        transactions: List[Transaction],
        currency: str = "IDR",
    ) -> Optional[bytes]:
        """Generate a 2-panel modern dark-theme financial summary chart."""
        try:
            # Set modern dark styling
            plt.style.use("dark_background")
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5), facecolor="#121826")
            fig.subplots_adjust(wspace=0.35)

            # --- Panel 1: Cash Flow & Buffer Growth ---
            categories_bar = ["Gross Income", "Total Expense", "Salary Drawn", "Buffer Fund", "Tax Reserve"]
            values_bar = [
                summary.total_income,
                summary.total_expense,
                summary.actual_salary_drawn,
                summary.buffer_fund_balance,
                summary.tax_reserve,
            ]
            colors_bar = ["#10B981", "#EF4444", "#3B82F6", "#8B5CF6", "#F59E0B"]

            bars = ax1.bar(categories_bar, values_bar, color=colors_bar, width=0.55, edgecolor="#ffffff", linewidth=0.5)
            ax1.set_title(f"Financial Flows ({summary.month_year})", fontsize=12, fontweight="bold", color="#E2E8F0", pad=12)
            ax1.set_facecolor("#1E293B")
            ax1.grid(axis="y", linestyle="--", alpha=0.2, color="#94A3B8")
            ax1.tick_params(axis="x", rotation=25, labelsize=9, colors="#CBD5E1")
            ax1.tick_params(axis="y", labelsize=8, colors="#94A3B8")
            ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{x:,.0f}"))

            # Label values on top of bars
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax1.annotate(
                        f"{height:,.0f}",
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha="center",
                        va="bottom",
                        fontsize=8,
                        color="#F8FAFC",
                        fontweight="bold",
                    )

            # --- Panel 2: Expense Category Breakdown ---
            cat_expenses: Dict[str, float] = {}
            for tx in transactions:
                if tx.type == TransactionType.EXPENSE:
                    cat_name = tx.category.value
                    cat_expenses[cat_name] = cat_expenses.get(cat_name, 0.0) + tx.amount

            if not cat_expenses or sum(cat_expenses.values()) == 0:
                ax2.text(
                    0.5,
                    0.5,
                    "No Expense Data Recorded",
                    ha="center",
                    va="center",
                    color="#94A3B8",
                    fontsize=11,
                )
                ax2.set_title("Expense Distribution", fontsize=12, fontweight="bold", color="#E2E8F0", pad=12)
                ax2.set_facecolor("#1E293B")
                ax2.axis("off")
            else:
                pie_labels = list(cat_expenses.keys())
                pie_values = list(cat_expenses.values())
                pie_colors = ["#38BDF8", "#F43F5E", "#FBBF24", "#A855F7", "#34D399"][: len(pie_labels)]

                wedges, texts, autotexts = ax2.pie(
                    pie_values,
                    labels=pie_labels,
                    autopct="%1.1f%%",
                    startangle=140,
                    colors=pie_colors,
                    wedgeprops={"edgecolor": "#121826", "linewidth": 2, "width": 0.65},
                    textprops={"color": "#E2E8F0", "fontsize": 9},
                )
                for autotext in autotexts:
                    autotext.set_color("#FFFFFF")
                    autotext.set_fontweight("bold")
                    autotext.set_fontsize(8)

                ax2.set_title("Expense Breakdown", fontsize=12, fontweight="bold", color="#E2E8F0", pad=12)

            # Save to memory buffer
            buf = io.BytesIO()
            plt.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()

        except Exception as e:
            logger.error("Error generating monthly chart: %s", e, exc_info=True)
            return None


chart_generator = ChartGenerator()
