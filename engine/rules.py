"""
Financial rules and thresholds configuration for Freelance AI Financial Engine.
"""

# Budget Guard Thresholds (percentages)
WARNING_THRESHOLD_PERCENT = 80.0
BREACH_THRESHOLD_PERCENT = 100.0

# Buffer Runway Safety Standards (in months of target living costs)
RUNWAY_CRITICAL = 1.0     # < 1 month: High alert
RUNWAY_MODERATE = 3.0     # 1-3 months: Rebuilding phase
RUNWAY_HEALTHY = 6.0      # 3-6 months: Ideal freelance safety cushion
RUNWAY_ABUNDANT = 12.0    # > 12 months: Surplus can be safely invested

# Category Allocation Guidelines for Freelancers
DEFAULT_TAX_PERCENT = 10.0
DEFAULT_SMOOTHING_BUFFER_PERCENT = 100.0  # All remaining surplus goes to buffer by default
