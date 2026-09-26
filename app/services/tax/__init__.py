"""Tax and financial-income projection services.

Phase 10.5 keeps projection logic separate from the existing tax-benefit
calculator so year-specific legal rules can evolve independently.
"""

from app.services.tax.financial_income import (
    FinancialIncomeProjectionError,
    build_financial_income_projection,
    get_financial_income_projection_for_user,
)
from app.services.tax.investment_tax import (
    ASSET_DOMESTIC_DIVIDEND_STOCK,
    ASSET_KR_LISTED_US_ETF,
    ASSET_US_DIRECT,
    InvestmentTaxComparisonError,
    compare_investment_tax_2026,
)

__all__ = [
    "FinancialIncomeProjectionError",
    "build_financial_income_projection",
    "get_financial_income_projection_for_user",
    "ASSET_DOMESTIC_DIVIDEND_STOCK",
    "ASSET_KR_LISTED_US_ETF",
    "ASSET_US_DIRECT",
    "InvestmentTaxComparisonError",
    "compare_investment_tax_2026",
]
