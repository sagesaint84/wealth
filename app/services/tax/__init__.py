"""Tax and financial-income projection services.

Phase 10.5 keeps projection logic separate from the existing tax-benefit
calculator so year-specific legal rules can evolve independently.
"""

from app.services.tax.financial_income import (
    FinancialIncomeProjectionError,
    build_financial_income_projection,
    get_financial_income_projection_for_user,
)

__all__ = [
    "FinancialIncomeProjectionError",
    "build_financial_income_projection",
    "get_financial_income_projection_for_user",
]
