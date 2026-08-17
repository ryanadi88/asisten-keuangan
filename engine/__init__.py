"""
Financial engine package initialization.
"""

from engine.financial_engine import (
    FreelanceFinancialEngine,
    financial_engine,
    render_progress_bar,
)
from engine.rules import (
    WARNING_THRESHOLD_PERCENT,
    BREACH_THRESHOLD_PERCENT,
    RUNWAY_CRITICAL,
    RUNWAY_MODERATE,
    RUNWAY_HEALTHY,
)
from engine.affordability_radar import AffordabilityRadar, affordability_radar
from engine.cashflow_forecaster import CashflowForecaster, cashflow_forecaster
from engine.currency_converter import CurrencyConverterEngine, currency_converter
from engine.tax_estimator import TaxEstimatorEngine, tax_estimator
from engine.pricing_calculator import PricingCalculatorEngine, pricing_calculator

__all__ = [
    "FreelanceFinancialEngine",
    "financial_engine",
    "render_progress_bar",
    "WARNING_THRESHOLD_PERCENT",
    "BREACH_THRESHOLD_PERCENT",
    "RUNWAY_CRITICAL",
    "RUNWAY_MODERATE",
    "RUNWAY_HEALTHY",
    "AffordabilityRadar",
    "affordability_radar",
    "CashflowForecaster",
    "cashflow_forecaster",
    "CurrencyConverterEngine",
    "currency_converter",
    "TaxEstimatorEngine",
    "tax_estimator",
    "PricingCalculatorEngine",
    "pricing_calculator",
]
