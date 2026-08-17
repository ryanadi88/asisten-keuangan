"""
Freelance Financial Engine logic module.
Executes dynamic income smoothing, tax reservation, salary floor allocation,
buffer fund pooling, and smart budget guardrail triggers.
"""

import logging
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

from config import settings, format_currency, get_current_month_year
from database.base import StorageBackend
from database import get_storage
from database.models import (
    Transaction,
    TransactionCreate,
    TransactionType,
    Category,
    MonthlySummary,
    UserSettings,
    BudgetGuardStatus,
    BudgetCheckResult,
    IncomeSplitResult,
    FinancialGoal,
    GoalAllocationItem,
    FinancialHealthReport,
)
from engine.rules import (
    WARNING_THRESHOLD_PERCENT,
    BREACH_THRESHOLD_PERCENT,
    RUNWAY_CRITICAL,
    RUNWAY_MODERATE,
    RUNWAY_HEALTHY,
)

logger = logging.getLogger(__name__)


class FreelanceFinancialEngine:
    def __init__(self, storage: Optional[StorageBackend] = None):
        self.storage = storage or get_storage()

    async def get_or_create_monthly_summary(self, user_id: int, month_year: Optional[str] = None) -> MonthlySummary:
        m_y = month_year or get_current_month_year()
        return await self.storage.get_monthly_summary(m_y, user_id)

    async def get_user_settings(self, user_id: int) -> UserSettings:
        return await self.storage.get_user_settings(user_id)

    async def check_budget_guard(
        self,
        user_id: int,
        category: Category,
        new_amount: float,
        month_year: Optional[str] = None,
    ) -> BudgetCheckResult:
        """
        Evaluate proposed expense against category budget threshold.
        Triggers 80% Warning and 100%+ Breach Alert.
        """
        m_y = month_year or get_current_month_year()
        user_settings = await self.get_user_settings(user_id)
        currency = user_settings.currency

        # Determine category limit
        if category == Category.NEEDS:
            budget_limit = user_settings.needs_budget
        elif category == Category.WANTS:
            budget_limit = user_settings.wants_budget
        elif category == Category.OPERATIONAL:
            budget_limit = user_settings.operational_budget
        else:
            # Buffer, Investment, Emergency don't have expense limits
            budget_limit = 0.0

        # Calculate current spending for this category in the month
        transactions = await self.storage.get_transactions(user_id=user_id, month_year=m_y, limit=500)
        current_spent = sum(
            tx.amount
            for tx in transactions
            if tx.type == TransactionType.EXPENSE and tx.category == category
        )

        total_spent = current_spent + new_amount

        if budget_limit <= 0:
            return BudgetCheckResult(
                category=category,
                current_spent=current_spent,
                new_amount=new_amount,
                total_spent=total_spent,
                budget_limit=budget_limit,
                percentage_used=0.0,
                status=BudgetGuardStatus.OK,
                message="No budget cap for this category.",
                remaining_budget=0.0,
            )

        pct_used = (total_spent / budget_limit) * 100.0
        remaining = budget_limit - total_spent

        if pct_used >= BREACH_THRESHOLD_PERCENT:
            status = BudgetGuardStatus.BREACH
            overage = total_spent - budget_limit
            msg = (
                f"🚨 *BUDGET BREACH ALERT ({pct_used:.1f}%)*\n"
                f"Pengeluaran kategori *{category.value}* telah melebihi batas anggaran "
                f"{format_currency(budget_limit, currency)}!\n"
                f"Kelebihan: *{format_currency(overage, currency)}*.\n"
                f"⚠️ *Perhatian:* Pengeluaran selanjutnya akan langsung memotong dana darurat / Buffer Fund!"
            )
        elif pct_used >= WARNING_THRESHOLD_PERCENT:
            status = BudgetGuardStatus.WARNING
            msg = (
                f"⚠️ *BUDGET GUARD WARNING ({pct_used:.1f}%)*\n"
                f"Kategori *{category.value}* sudah mencapai {pct_used:.1f}% dari batas "
                f"{format_currency(budget_limit, currency)}.\n"
                f"Sisa kuota aman bulan ini: *{format_currency(max(0.0, remaining), currency)}*."
            )
        else:
            status = BudgetGuardStatus.OK
            msg = (
                f"✅ Budget OK ({pct_used:.1f}% digunakan). "
                f"Sisa kuota: {format_currency(remaining, currency)}."
            )

        return BudgetCheckResult(
            category=category,
            current_spent=current_spent,
            new_amount=new_amount,
            total_spent=total_spent,
            budget_limit=budget_limit,
            percentage_used=round(pct_used, 1),
            status=status,
            message=msg,
            remaining_budget=remaining,
        )

    async def process_income(
        self,
        tx_create: TransactionCreate,
        month_year: Optional[str] = None,
    ) -> Tuple[Transaction, IncomeSplitResult]:
        """
        Dynamic Income Splitter:
        1. Deduct Operational/Tax Reserve (e.g. 10%).
        2. Allocate Base Salary floor up to Target Salary for the month.
        3. Funnel all remaining surplus directly into the Buffer Fund / Smoothing Pool.
        """
        m_y = month_year or tx_create.timestamp.strftime("%Y-%m")
        user_id = tx_create.user_id
        gross_amount = tx_create.amount

        # 1. Fetch user settings and current month summary
        user_settings = await self.get_user_settings(user_id)
        summary = await self.get_or_create_monthly_summary(user_id, m_y)
        currency = user_settings.currency

        # 2. Tax / Operational Reserve calculation
        tax_rate = user_settings.tax_percentage
        tax_amount = gross_amount * (tax_rate / 100.0)
        net_income = gross_amount - tax_amount

        # 3. Active Goals Auto-Split Allocation
        active_goals = await self.storage.get_goals(user_id, is_completed=False)
        goal_allocations: List[GoalAllocationItem] = []
        total_goals_allocated = 0.0

        for goal in active_goals:
            if goal.allocation_percent > 0 and net_income > total_goals_allocated:
                alloc_val = min(
                    net_income - total_goals_allocated,
                    gross_amount * (goal.allocation_percent / 100.0),
                    goal.remaining_amount
                )
                if alloc_val > 0:
                    goal.current_amount += alloc_val
                    total_goals_allocated += alloc_val
                    is_now_comp = goal.current_amount >= goal.target_amount
                    goal.is_completed = is_now_comp
                    await self.storage.update_goal(goal)
                    goal_allocations.append(
                        GoalAllocationItem(
                            goal_id=goal.id,
                            goal_name=goal.name,
                            allocated_amount=alloc_val,
                            new_current_amount=goal.current_amount,
                            target_amount=goal.target_amount,
                            percentage_achieved=goal.percentage_achieved,
                            is_now_completed=is_now_comp,
                        )
                    )

        remaining_income = max(0.0, net_income - total_goals_allocated)

        # 4. Base Salary Draw calculation
        target_salary = user_settings.target_salary
        drawn_so_far = summary.actual_salary_drawn
        salary_quota_left = max(0.0, target_salary - drawn_so_far)

        salary_allocated = min(remaining_income, salary_quota_left)
        surplus_buffer = max(0.0, remaining_income - salary_allocated)

        # 5. Update Summary Balances
        new_total_income = summary.total_income + gross_amount
        new_tax_reserve = summary.tax_reserve + tax_amount
        new_actual_drawn = summary.actual_salary_drawn + salary_allocated
        new_buffer_balance = summary.buffer_fund_balance + surplus_buffer

        summary.total_income = new_total_income
        summary.tax_reserve = new_tax_reserve
        summary.actual_salary_drawn = new_actual_drawn
        summary.buffer_fund_balance = new_buffer_balance
        summary.target_salary = target_salary

        await self.storage.save_monthly_summary(summary)

        # 6. Save Transaction Record
        notes_detail = (
            f"Gross: {format_currency(gross_amount, currency)} | "
            f"Tax ({tax_rate}%): {format_currency(tax_amount, currency)} | "
            f"Goals: {format_currency(total_goals_allocated, currency)} | "
            f"Salary: {format_currency(salary_allocated, currency)} | "
            f"Buffer: {format_currency(surplus_buffer, currency)}"
        )
        if tx_create.notes:
            tx_create.notes = f"{tx_create.notes} | {notes_detail}"
        else:
            tx_create.notes = notes_detail

        persisted_tx = await self.storage.add_transaction(tx_create)

        # 7. Build Result Message
        target_met = new_actual_drawn >= target_salary
        runway = round(new_buffer_balance / target_salary, 1) if target_salary > 0 else 0.0

        goals_block = ""
        if goal_allocations:
            g_lines = []
            for ga in goal_allocations:
                check_icon = "🎉 *SELESAI!*" if ga.is_now_completed else f"{render_progress_bar(ga.percentage_achieved)}"
                g_lines.append(
                    f"• *{ga.goal_name}:* `+{format_currency(ga.allocated_amount, currency)}`\n"
                    f"  {check_icon} ({format_currency(ga.new_current_amount, currency)} / {format_currency(ga.target_amount, currency)})"
                )
            goals_block = (
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 *AUTO-SPLIT TARGET & WISHLIST:*\n"
                + "\n".join(g_lines) + "\n"
            )

        split_msg = (
            f"💸 *INCOME DYNAMIC SPLIT REPORT*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *Gross Income:* `{format_currency(gross_amount, currency)}`\n"
            f"🏛️ *Tax & Ops Reserve ({tax_rate}%):* `{format_currency(tax_amount, currency)}`\n"
            f"💵 *Net Income:* `{format_currency(net_income, currency)}`\n"
            f"{goals_block}"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 *Alokasi Gaji Bulanan:* `{format_currency(salary_allocated, currency)}` "
            f"({format_currency(new_actual_drawn, currency)} / {format_currency(target_salary, currency)})\n"
            f"🛡️ *Surplus masuk Buffer Fund:* `{format_currency(surplus_buffer, currency)}`\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *Total Buffer Fund:* `{format_currency(new_buffer_balance, currency)}`\n"
            f"⏳ *Buffer Runway:* `{runway} Bulan Biaya Hidup`\n"
            f"{'🎉 *Target Gaji Bulan Ini Telah Tercapai 100%!*' if target_met else '⏳ *Mengisi kuota gaji minimum bulan ini.*'}"
        )

        split_result = IncomeSplitResult(
            gross_income=gross_amount,
            tax_reserve_amount=tax_amount,
            tax_percentage=tax_rate,
            net_income=net_income,
            salary_drawn_allocated=salary_allocated,
            target_salary=target_salary,
            total_salary_drawn_month=new_actual_drawn,
            salary_target_met=target_met,
            buffer_pool_allocated=surplus_buffer,
            current_buffer_balance=new_buffer_balance,
            buffer_runway_months=runway,
            message=split_msg,
        )

        return persisted_tx, split_result

    async def process_expense(
        self,
        tx_create: TransactionCreate,
        month_year: Optional[str] = None,
    ) -> Tuple[Transaction, BudgetCheckResult]:
        """
        Record expense and evaluate against smart budget guardrails.
        """
        m_y = month_year or tx_create.timestamp.strftime("%Y-%m")
        user_id = tx_create.user_id

        # 1. Guard check
        guard_result = await self.check_budget_guard(
            user_id=user_id,
            category=tx_create.category,
            new_amount=tx_create.amount,
            month_year=m_y,
        )

        # 2. Persist transaction
        persisted_tx = await self.storage.add_transaction(tx_create)

        # 3. Update summary
        summary = await self.get_or_create_monthly_summary(user_id, m_y)
        summary.total_expense += tx_create.amount

        # If expense category is Investment/Emergency/Buffer draw
        if tx_create.category == Category.INVESTMENT:
            summary.investment_total += tx_create.amount
        elif tx_create.category == Category.EMERGENCY:
            summary.emergency_fund += tx_create.amount
        elif tx_create.category == Category.BUFFER and tx_create.amount < 0:
            # Withdrawing from buffer
            summary.buffer_fund_balance += tx_create.amount

        await self.storage.save_monthly_summary(summary)

        return persisted_tx, guard_result

    async def draw_salary_from_buffer(
        self,
        user_id: int,
        amount: Optional[float] = None,
        month_year: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Income smoothing feature: In a dry/lean freelance month, draw needed base salary
        from the accumulated buffer pool into the current month's salary drawn.
        """
        m_y = month_year or get_current_month_year()
        summary = await self.get_or_create_monthly_summary(user_id, m_y)
        user_settings = await self.get_user_settings(user_id)
        currency = user_settings.currency

        needed_salary = max(0.0, summary.target_salary - summary.actual_salary_drawn)
        draw_amount = amount if (amount is not None and amount > 0) else needed_salary

        if draw_amount <= 0:
            return False, "Target gaji bulan ini sudah terpenuhi penuh. Tidak perlu penarikan Buffer Fund."

        if summary.buffer_fund_balance < draw_amount:
            return False, (
                f"Saldo Buffer Fund tidak mencukupi! Saldo saat ini: {format_currency(summary.buffer_fund_balance, currency)}, "
                f"diperlukan: {format_currency(draw_amount, currency)}."
            )

        # Execute transfer from Buffer Fund to Salary Drawn
        summary.buffer_fund_balance -= draw_amount
        summary.actual_salary_drawn += draw_amount
        await self.storage.save_monthly_summary(summary)

        # Log as internal smoothing transaction
        await self.storage.add_transaction(
            TransactionCreate(
                user_id=user_id,
                type=TransactionType.INCOME,
                category=Category.BUFFER,
                amount=draw_amount,
                source_or_merchant="Buffer Fund Smoothing Draw",
                notes=f"Penarikan dana smoothing untuk gaji bulan {m_y}",
            )
        )

        runway = summary.buffer_runway_months
        msg = (
            f"🛡️ *INCOME SMOOTHING DITERAPKAN*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Berhasil menarik `{format_currency(draw_amount, currency)}` dari Buffer Fund.\n"
            f"🎯 Total gaji ditarik bulan ini: `{format_currency(summary.actual_salary_drawn, currency)}` / `{format_currency(summary.target_salary, currency)}`\n"
            f"🛡️ Sisa Saldo Buffer Fund: `{format_currency(summary.buffer_fund_balance, currency)}` ({runway} Bulan Runway)"
        )
        return True, msg

    async def get_financial_health(self, user_id: int, month_year: Optional[str] = None) -> Dict[str, Any]:
        """Compute freelance financial health metrics and recommendations."""
        m_y = month_year or get_current_month_year()
        summary = await self.get_or_create_monthly_summary(user_id, m_y)
        user_settings = await self.get_user_settings(user_id)
        currency = user_settings.currency

        runway = summary.buffer_runway_months
        salary_pct = (
            (summary.actual_salary_drawn / summary.target_salary) * 100.0
            if summary.target_salary > 0
            else 100.0
        )

        if runway >= RUNWAY_HEALTHY:
            health_badge = "🟢 SANGAT SEHAT (Anti-Resesi)"
            health_advice = "Kondisi keuangan freelance sangat stabil. Anda aman dari fluktuasi order hingga 6+ bulan kedepan. Surplus berikutnya dapat dialokasikan ke investasi."
        elif runway >= RUNWAY_MODERATE:
            health_badge = "🟡 STABIL & AMAN"
            health_advice = "Buffer fund cukup untuk mengamankan 3 bulan kedepan. Pertahankan disiplin alokasi surplus ke buffer pool."
        else:
            health_badge = "🔴 BUTUH PERKUATAN (Vulnerable)"
            health_advice = "Buffer fund masih di bawah 3 bulan biaya hidup. Prioritaskan seluruh surplus freelance untuk mengisi Buffer Fund sebelum pengeluaran non-primer."

        return {
            "month_year": m_y,
            "currency": currency,
            "summary": summary,
            "settings": user_settings,
            "runway_months": runway,
            "salary_pct": round(salary_pct, 1),
            "health_badge": health_badge,
            "health_advice": health_advice,
        }

    async def get_daily_safe_spend(self, user_id: int, month_year: Optional[str] = None) -> Dict[str, Any]:
        """Compute days remaining in the month and daily safe-to-spend allowance."""
        import calendar
        m_y = month_year or get_current_month_year()
        now = datetime.now()
        year, month = int(m_y.split("-")[0]), int(m_y.split("-")[1])
        _, total_days = calendar.monthrange(year, month)

        current_day = now.day if (now.year == year and now.month == month) else 1
        days_remaining = max(1, total_days - current_day + 1)

        user_settings = await self.get_user_settings(user_id)
        currency = user_settings.currency
        transactions = await self.storage.get_transactions(user_id=user_id, month_year=m_y, limit=500)

        needs_spent = sum(tx.amount for tx in transactions if tx.type == TransactionType.EXPENSE and tx.category == Category.NEEDS)
        wants_spent = sum(tx.amount for tx in transactions if tx.type == TransactionType.EXPENSE and tx.category == Category.WANTS)
        total_living_spent = needs_spent + wants_spent
        total_living_budget = user_settings.needs_budget + user_settings.wants_budget

        remaining_living_budget = max(0.0, total_living_budget - total_living_spent)
        daily_safe_limit = round(remaining_living_budget / days_remaining, 0)

        # Today's spending
        today_str = now.strftime("%Y-%m-%d")
        today_spent = sum(
            tx.amount for tx in transactions
            if tx.type == TransactionType.EXPENSE and tx.timestamp.strftime("%Y-%m-%d") == today_str
        )

        return {
            "month_year": m_y,
            "current_day": current_day,
            "total_days": total_days,
            "days_remaining": days_remaining,
            "needs_spent": needs_spent,
            "wants_spent": wants_spent,
            "total_living_spent": total_living_spent,
            "total_living_budget": total_living_budget,
            "remaining_living_budget": remaining_living_budget,
            "daily_safe_limit": daily_safe_limit,
            "today_spent": today_spent,
            "currency": currency,
        }

    async def revert_transaction(self, tx_id: str, user_id: int) -> Tuple[bool, str, Optional[Transaction]]:
        """Revert/Delete a transaction and restore monthly summary balances."""
        tx = await self.storage.get_transaction_by_id(tx_id, user_id)
        if not tx:
            return False, "⚠️ Transaksi tidak ditemukan atau sudah dibatalkan sebelumnya.", None

        m_y = tx.timestamp.strftime("%Y-%m")
        summary = await self.get_or_create_monthly_summary(user_id, m_y)
        user_settings = await self.get_user_settings(user_id)
        currency = user_settings.currency

        # 1. Update balances based on type
        if tx.type == TransactionType.EXPENSE:
            summary.total_expense = max(0.0, summary.total_expense - tx.amount)
            if tx.category == Category.INVESTMENT:
                summary.investment_total = max(0.0, summary.investment_total - tx.amount)
            elif tx.category == Category.EMERGENCY:
                summary.emergency_fund = max(0.0, summary.emergency_fund - tx.amount)
        elif tx.type == TransactionType.INCOME:
            tax_rate = user_settings.tax_percentage
            tax_amount = tx.amount * (tax_rate / 100.0)
            net_income = tx.amount - tax_amount

            summary.total_income = max(0.0, summary.total_income - tx.amount)
            summary.tax_reserve = max(0.0, summary.tax_reserve - tax_amount)
            summary.actual_salary_drawn = max(0.0, summary.actual_salary_drawn - net_income)

        await self.storage.save_monthly_summary(summary)

        # 2. Delete transaction record from backend
        deleted = await self.storage.delete_transaction(tx_id, user_id)
        if not deleted:
            return False, "⚠️ Gagal menghapus transaksi dari database.", None

        msg = (
            f"↩️ *TRANSAKSI BERHASIL DIBATALKAN*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🗑️ Transaksi `{tx.id}` ({tx.type.value} *{format_currency(tx.amount, currency)}* - _{tx.source_or_merchant}_) "
            f"telah dihapus dari pembukuan dan Google Sheets."
        )
        return True, msg, tx

    def calculate_goal_eta(self, goal: FinancialGoal, avg_monthly_income: float) -> str:
        """Estimate completion month/year for a financial goal based on average monthly income."""
        if goal.is_completed or goal.remaining_amount <= 0:
            return "🎉 Sudah Tercapai!"

        if avg_monthly_income <= 0 or goal.allocation_percent <= 0:
            return "Perlu ada alokasi pemasukan aktif"

        monthly_goal_contribution = avg_monthly_income * (goal.allocation_percent / 100.0)
        if monthly_goal_contribution <= 0:
            return "Belum dapat diprediksi"

        months_needed = goal.remaining_amount / monthly_goal_contribution
        months_ceil = max(1, int(round(months_needed + 0.49)))

        if months_ceil == 1:
            return "Bulan ini / 1 Bulan lagi! 🚀"
        elif months_ceil < 12:
            return f"± {months_ceil} Bulan lagi"
        else:
            years = round(months_ceil / 12, 1)
            return f"± {years} Tahun lagi ({months_ceil} Bulan)"

    async def calculate_financial_health_score(self, user_id: int) -> FinancialHealthReport:
        """Compute an objective 0-100 financial health score for a freelancer."""
        m_y = get_current_month_year()
        summary = await self.get_or_create_monthly_summary(user_id, m_y)
        user_settings = await self.get_user_settings(user_id)
        currency = user_settings.currency
        transactions = await self.storage.get_transactions(user_id=user_id, month_year=m_y, limit=500)
        subscriptions = await self.storage.get_subscriptions(user_id=user_id, is_active=True)
        goals = await self.storage.get_goals(user_id=user_id, is_completed=False)

        # 1. Runway Score (Max 35)
        runway = summary.buffer_runway_months
        if runway >= 6.0:
            runway_pts = 35.0
        elif runway >= 3.0:
            runway_pts = 25.0
        elif runway >= 1.0:
            runway_pts = 15.0
        else:
            runway_pts = 5.0

        # 2. Savings / Buffer Rate (Max 25)
        income = summary.total_income
        expense = summary.total_expense
        savings = income - expense
        savings_rate = (savings / income * 100.0) if income > 0 else 0.0

        if savings_rate >= 30.0:
            savings_pts = 25.0
        elif savings_rate >= 15.0:
            savings_pts = 18.0
        elif savings_rate > 0.0:
            savings_pts = 10.0
        else:
            savings_pts = 0.0

        # 3. Spending Discipline vs Budget (Max 25)
        needs_spent = sum(tx.amount for tx in transactions if tx.type == TransactionType.EXPENSE and tx.category == Category.NEEDS)
        wants_spent = sum(tx.amount for tx in transactions if tx.type == TransactionType.EXPENSE and tx.category == Category.WANTS)
        needs_ok = needs_spent <= user_settings.needs_budget
        wants_ok = wants_spent <= user_settings.wants_budget

        if needs_ok and wants_ok:
            discipline_pts = 25.0
        elif needs_ok or wants_ok:
            discipline_pts = 14.0
        else:
            discipline_pts = 5.0

        # 4. Tax & Fixed Cost Stability (Max 15)
        tax_pts = 15.0 if summary.tax_reserve > 0 else 8.0

        total_score = int(round(runway_pts + savings_pts + discipline_pts + tax_pts))
        total_score = max(0, min(100, total_score))

        if total_score >= 90:
            grade = "A+"
            label = "🛡️ Benteng Finansial Super Kuat"
        elif total_score >= 75:
            grade = "A"
            label = "🌟 Keuangan Sangat Sehat & Stabil"
        elif total_score >= 60:
            grade = "B"
            label = "⚖️ Kondisi Finansial Cukup Baik"
        elif total_score >= 40:
            grade = "C"
            label = "⚠️ Perlu Penghematan & Penambahan Buffer"
        else:
            grade = "D"
            label = "🚨 Status Waspada: Perlu Evaluasi Pengeluaran"

        recs = []
        if runway < 3.0:
            recs.append("Perkuat Buffer Runway minimal mencapai 3-6 bulan biaya hidup.")
        if not wants_ok:
            recs.append("Kategori Wants (keinginan/kopi/hiburan) melebihi kuota. Rem pengeluaran konsumtif.")
        if not goals:
            recs.append("Buat target impian baru dengan /add_goal untuk memotivasi produktivitas freelance.")
        if not recs:
            recs.append("Pertahankan alokasi keuangan disiplin Anda saat ini!")

        summary_text = (
            f"📊 *SKOR KESEHATAN KEUANGAN FREELANCE*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 *Total Skor:* `{total_score}/100` (Grade: *{grade}*)\n"
            f"🏷️ *Status:* *{label}*\n\n"
            f"📈 *Rincian Penilaian:*\n"
            f"• 🛡️ Buffer Runway ({runway} Bln): `{runway_pts:.0f}/35 Poin`\n"
            f"• 💰 Tingkat Tabungan ({savings_rate:.1f}%): `{savings_pts:.0f}/25 Poin`\n"
            f"• 🎯 Kedisiplinan Anggaran: `{discipline_pts:.0f}/25 Poin`\n"
            f"• 🏛️ Cadangan Pajak: `{tax_pts:.0f}/15 Poin`\n\n"
            f"💡 *Rekomendasi Strategis:*\n"
            + "\n".join([f"• {r}" for r in recs])
        )

        return FinancialHealthReport(
            score=total_score,
            grade=grade,
            grade_label=label,
            runway_months=runway,
            runway_score=runway_pts,
            savings_rate_score=savings_pts,
            discipline_score=discipline_pts,
            tax_discipline_score=tax_pts,
            recommendations=recs,
            summary_text=summary_text,
        )


def render_progress_bar(percentage: float, width: int = 10) -> str:
    """Render a sleek ASCII visual progress bar e.g. [████████░░] 80.0%."""
    pct = max(0.0, percentage)
    filled_len = min(width, int(round((pct / 100.0) * width)))
    empty_len = max(0, width - filled_len)
    bar = "█" * filled_len + "░" * empty_len
    return f"`[{bar}]` *{percentage:.1f}%*"


financial_engine = FreelanceFinancialEngine()
