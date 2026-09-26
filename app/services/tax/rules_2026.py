"""2026 financial-income and high-dividend special-tax rules.

Only rules that are backed by official 2026 sources belong here. Product UI
must consume these constants through service output rather than hard-coding tax
thresholds or rates.
"""

RULE_YEAR = 2026

# Product warning threshold. This is not a statutory tax threshold; it is an
# early-warning marker used to surface that annual financial income is moving
# materially closer to the statutory comprehensive-tax threshold.
FINANCIAL_INCOME_WATCH_THRESHOLD_KRW = 10_000_000

# Statutory comprehensive taxation threshold for annual taxable financial
# income (interest + dividend income). Separately taxed / non-taxable income is
# excluded when the applicable legal treatment is positively identified.
FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW = 20_000_000

# Personal comprehensive-income basic rates. These rates are only used by the
# B-4 input-based comparison helper; that helper does not reconstruct a final
# financial-income comprehensive-tax return.
PERSONAL_COMPREHENSIVE_INCOME_TAX_BRACKETS = (
    (14_000_000, 0.06),
    (50_000_000, 0.15),
    (88_000_000, 0.24),
    (150_000_000, 0.35),
    (300_000_000, 0.38),
    (500_000_000, 0.40),
    (1_000_000_000, 0.42),
    (None, 0.45),
)

# Dividend gross-up rate under Income Tax Act Article 17(3). The Article 56
# dividend tax credit is based on the gross-up amount, subject to the official
# financial-income return form's comparison-tax ceiling.
DIVIDEND_GROSS_UP_RATE = 0.10

# 2026 high-dividend-company special separate-taxation brackets.
# These are national income-tax rates only. Local income tax is separate and is
# deliberately not folded into this rule table.
HIGH_DIVIDEND_SPECIAL_TAX_BRACKETS = (
    (20_000_000, 0.14),
    (300_000_000, 0.20),
    (5_000_000_000, 0.25),
    (None, 0.30),
)

# High-dividend-company statutory qualification headline tests. The product
# does not infer company eligibility from market data; qualification should be
# confirmed from the issuer's KIND disclosure / official filing.
HIGH_DIVIDEND_PAYOUT_RATIO_PRIMARY_PCT = 40.0
HIGH_DIVIDEND_PAYOUT_RATIO_GROWTH_ROUTE_PCT = 25.0
HIGH_DIVIDEND_DIVIDEND_GROWTH_ROUTE_PCT = 10.0
HIGH_DIVIDEND_SPECIAL_FIRST_PAYMENT_DATE = "2026-01-01"
HIGH_DIVIDEND_SPECIAL_LAST_QUALIFYING_BUSINESS_YEAR_END = "2028-12-31"

# Official basis verified 2026-09-26:
# 1) 국가법령정보센터, 소득세법 시행규칙 별지 제40호서식(1)
#    - 금융소득 종합과세기준금액 20,000,000원
#    - 비과세/분리과세 이자·배당소득은 작성 대상에서 제외
# 2) 조세특례제한법 제104조의27
#    - 고배당기업 특례배당소득은 신청 시 종합소득과세표준에 합산하지 않음
#    - 상장법인(코넥스 제외), 배당 유지 및 배당성향/증가 요건 등 규정
# 3) 조세특례제한법 시행령 제104조의24
#    - 특례배당소득 범위, 배당성향 산정 및 분리과세 신청 절차
# 4) 국세청 2026-03-09 안내
#    - 특례배당소득 세율: 14% / 20% / 25% / 30% (지방세 별도)
#    - 분리과세 신청 시 해당 특례배당은 금융소득 2천만원 초과 판정에서 제외
OFFICIAL_RULE_SOURCE_URL = (
    "https://law.go.kr/LSW/flDownload.do?bylClsCd=110202&flSeq=151083979&gubun="
)
OFFICIAL_PERSONAL_COMPREHENSIVE_TAX_RATE_SOURCE_URL = (
    "https://www.law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1026637493"
)
OFFICIAL_FINANCIAL_INCOME_RETURN_FORM_SOURCE_URL = (
    "https://law.go.kr/LSW/flDownload.do?bylClsCd=110202&flSeq=153744873&gubun="
)
OFFICIAL_DIVIDEND_TAX_CREDIT_LAW_SOURCE_URL = (
    "https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1032880527"
)
OFFICIAL_DIVIDEND_TAX_CREDIT_ENFORCEMENT_SOURCE_URL = (
    "https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=02&joNo=0116&lsiSeq=286211&urlMode=lsScJoRltInfoR"
)
OFFICIAL_PREPAID_WITHHOLDING_LAW_SOURCE_URL = (
    "https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1032881459"
)
OFFICIAL_HIGH_DIVIDEND_LAW_SOURCE_URL = (
    "https://www.law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1033275259"
)
OFFICIAL_HIGH_DIVIDEND_ENFORCEMENT_SOURCE_URL = (
    "https://law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1032481661"
)
OFFICIAL_HIGH_DIVIDEND_SOURCE_URL = (
    "https://www.nts.go.kr/nts/na/ntt/selectNttInfo.do?nttSn=1349597"
)
RULE_VERIFIED_ON = "2026-09-26"
DIVIDEND_TAX_CREDIT_VERIFIED_ON = "2026-09-27"
PREPAID_FINANCIAL_WITHHOLDING_VERIFIED_ON = "2026-09-27"
