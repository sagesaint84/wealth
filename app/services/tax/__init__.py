"""Tax and financial-income projection services.

Phase 10.5 keeps projection logic separate from the existing tax-benefit
calculator so year-specific legal rules can evolve independently.
"""

from app.services.tax.financial_income import (
    FinancialIncomeProjectionError,
    build_financial_income_projection,
    get_financial_income_projection_for_user,
)
from app.services.tax.family_financial_income import (
    FamilyFinancialIncomeRiskError,
    build_family_financial_income_risk,
    get_family_financial_income_risk_for_user,
)
from app.services.tax.high_dividend_2026 import (
    HighDividendSpecialTaxError,
    calculate_high_dividend_separate_tax_2026,
)
from app.services.tax.investment_tax import (
    ASSET_DOMESTIC_DIVIDEND_STOCK,
    ASSET_KR_LISTED_US_ETF,
    ASSET_US_DIRECT,
    InvestmentTaxComparisonError,
    compare_investment_tax_2026,
)
from app.services.tax.what_if import (
    FinancialIncomeWhatIfError,
    build_financial_income_what_if,
    get_financial_income_what_if_for_user,
)

__all__ = [
    "FinancialIncomeProjectionError",
    "build_financial_income_projection",
    "get_financial_income_projection_for_user",
    "FamilyFinancialIncomeRiskError",
    "build_family_financial_income_risk",
    "get_family_financial_income_risk_for_user",
    "HighDividendSpecialTaxError",
    "calculate_high_dividend_separate_tax_2026",
    "ASSET_DOMESTIC_DIVIDEND_STOCK",
    "ASSET_KR_LISTED_US_ETF",
    "ASSET_US_DIRECT",
    "InvestmentTaxComparisonError",
    "compare_investment_tax_2026",
    "FinancialIncomeWhatIfError",
    "build_financial_income_what_if",
    "get_financial_income_what_if_for_user",
]
