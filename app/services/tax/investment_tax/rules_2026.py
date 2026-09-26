"""2026 rules used by the investment-tax comparison screening engine.

The constants in this module are intentionally narrow.  They are not a full
Korean tax-law implementation; they support a side-by-side screening view for
personal investing versus a Korean family corporation.
"""

RULE_YEAR = 2026
RULE_VERIFIED_ON = "2026-09-26"

# Personal financial-income screening / withholding.
FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW = 20_000_000
GENERAL_DIVIDEND_INCOME_TAX_RATE = 0.14
GENERAL_DIVIDEND_LOCAL_TAX_RATE = 0.014
GENERAL_DIVIDEND_WITHHOLDING_RATE = 0.154

# Foreign listed shares: annual basic capital-gains deduction and ordinary
# non-major-shareholder foreign-share rates used for screening.
FOREIGN_SHARE_CAPITAL_GAIN_DEDUCTION_KRW = 2_500_000
FOREIGN_SHARE_CAPITAL_GAIN_INCOME_TAX_RATE = 0.20
FOREIGN_SHARE_CAPITAL_GAIN_LOCAL_TAX_RATE = 0.02
FOREIGN_SHARE_CAPITAL_GAIN_COMBINED_RATE = 0.22

# Korea-US treaty dividend withholding.  The 10% corporate rate has additional
# treaty conditions and is never assumed automatically by the engine.
US_TREATY_GENERAL_DIVIDEND_RATE = 0.15
US_TREATY_QUALIFIED_CORPORATE_DIVIDEND_RATE = 0.10

# Korean corporate income tax brackets: (upper bound, marginal rate).
# None means no upper bound.
CORPORATE_INCOME_TAX_BRACKETS = (
    (200_000_000, 0.10),
    (20_000_000_000, 0.20),
    (300_000_000_000, 0.22),
    (None, 0.25),
)
CORPORATE_LOCAL_INCOME_TAX_BRACKETS = (
    (200_000_000, 0.01),
    (20_000_000_000, 0.02),
    (300_000_000_000, 0.022),
    (None, 0.025),
)

# Domestic-corporation dividend received deduction / exclusion screening.
DOMESTIC_DIVIDEND_EXCLUSION_TIERS = (
    (50.0, 1.00),
    (20.0, 0.80),
    (0.0, 0.30),
)
DOMESTIC_DIVIDEND_MIN_HOLDING_MONTHS = 3

# Foreign-subsidiary dividend exclusion.  Eligibility is not inferred merely
# from ownership: callers must explicitly assert that the statutory conditions
# are satisfied.
FOREIGN_SUBSIDIARY_MIN_OWNERSHIP_PCT = 10.0
FOREIGN_SUBSIDIARY_DIVIDEND_EXCLUSION_RATE = 0.95

OFFICIAL_SOURCES = {
    "financial_income_threshold": "https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1027819291",
    "dividend_withholding": "https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1032881117",
    "withholding_local_tax": "https://www.law.go.kr/LSW/lsLawLinkInfo.do?chrClsCd=010202&lsId=001649&lsJoLnkSeq=1000226093&print=print",
    "foreign_share_basic_deduction": "https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1031623847",
    "foreign_share_rate": "https://www.law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1032205223",
    "foreign_share_local_rate": "https://law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1026498441",
    "corporate_tax_rate": "https://www.law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1029618963",
    "corporate_local_tax_rate": "https://www.law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1029490341",
    "domestic_dividend_exclusion": "https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1031669677",
    "domestic_dividend_holding_rule": "https://law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1028457233",
    "foreign_subsidiary_dividend_exclusion": "https://www.law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1032170043",
    "corporate_foreign_tax_credit": "https://www.law.go.kr/flDownload.do?flSeq=124451313&gubun=",
    "kr_fund_tax_basis": "https://law.go.kr/lumLsLinkPop.do?chrClsCd=010202&lspttninfSeq=114973",
    "korea_us_treaty": "https://www.irs.gov/pub/irs-trty/korea.pdf",
}
