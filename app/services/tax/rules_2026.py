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

# Local Tax Act Article 92(1) standard rates for comprehensive individual local
# income tax. A local government may vary these rates by ordinance within 50%
# under Article 92(2), so the B-4.4 comparison helper reports standard-rate
# results only and does not infer a taxpayer's ordinance-adjusted rate.
LOCAL_PERSONAL_COMPREHENSIVE_INCOME_TAX_STANDARD_BRACKETS = (
    (14_000_000, 0.006),
    (50_000_000, 0.015),
    (88_000_000, 0.024),
    (150_000_000, 0.035),
    (300_000_000, 0.038),
    (500_000_000, 0.040),
    (1_000_000_000, 0.042),
    (None, 0.045),
)

# Dividend gross-up rate under Income Tax Act Article 17(3). The Article 56
# dividend tax credit is based on the gross-up amount, subject to the official
# financial-income return form's comparison-tax ceiling.
DIVIDEND_GROSS_UP_RATE = 0.10

# Local Tax Special Treatment Control Act Article 95(1): the local dividend tax
# credit equals 10% of the amount added to gross receipts under Income Tax Act
# Article 17(3). The eligible dividend base is limited by Article 95(3) to the
# dividend income included in the comprehensive tax base above the statutory
# financial-income threshold.
LOCAL_DIVIDEND_TAX_CREDIT_RATE_ON_GROSS_UP = 0.10

# Local Tax Special Treatment Control Act Article 97(1): when national foreign
# tax credit is taken under Income Tax Act Article 57(1)(1), the corresponding
# comprehensive individual local-income-tax credit is 10% of the national
# credit amount. Article 97(2) provides a separate five-year local carryforward
# rule for qualifying excess amounts; B-4.6 does not calculate that carryforward.
LOCAL_FOREIGN_TAX_CREDIT_RATE_ON_NATIONAL_CREDIT = 0.10
LOCAL_FOREIGN_TAX_CREDIT_CARRYFORWARD_YEARS = 5

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

# Official basis verified 2026-09-27:
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
# 5) 소득세법 제57조, 제60조, 시행령 제117조, 시행규칙 별지 제11호서식
#    - 국외원천소득과 종합소득금액 비율로 국세 외국납부세액공제 한도 계산
#    - 국가별 한도, 대응비용, 조세조약상 공제대상세액, 10년 이월 구조를 구분
#    - 세액감면/비이월 세액공제/이월 세액공제의 적용순서를 별도 확인
# 6) 지방세특례제한법 제97조ㆍ제167조의2, 같은 법 시행령 제48조
#    - 국세 외국납부세액공제액의 10%를 종합소득 개인지방소득세에서 공제
#    - 제97조 제2항의 지방 외국납부세액공제 이월기간은 5년
#    - 소득세법 제57조 제1항 제2호 비용처리 방식이면 제97조 제1항 미적용
# 7) 소득세법 제65조ㆍ제76조 제3항 제1호ㆍ제85조 제4항, 별지 제40호서식(1)
#    - 중간예납세액은 확정신고납부 시 공제되는 기납부세액
#    - 신고서에서도 중간예납세액을 기납부세액으로 별도 표시
#    - 실제 반영액은 전년도 세액에서 제품이 자동 추정하지 않고 명시 입력
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
    "https://www.law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1032880527"
)
OFFICIAL_DIVIDEND_TAX_CREDIT_ENFORCEMENT_SOURCE_URL = (
    "https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=02&joNo=0116&lsiSeq=286211&urlMode=lsScJoRltInfoR"
)
OFFICIAL_PREPAID_WITHHOLDING_LAW_SOURCE_URL = (
    "https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1032881459"
)
OFFICIAL_INTERIM_PREPAYMENT_LAW_SOURCE_URL = (
    "https://www.law.go.kr/lsLawLinkInfo.do?chrClsCd=010202&lsJoLnkSeq=900034264"
)
OFFICIAL_FINAL_RETURN_PREPAID_TAX_LAW_SOURCE_URL = (
    "https://law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1032881375"
)
OFFICIAL_INCOME_TAX_REFUND_LAW_SOURCE_URL = (
    "https://law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1029626425"
)
OFFICIAL_INTERIM_PREPAYMENT_RETURN_FORM_SOURCE_URL = (
    "https://www.law.go.kr/LSW/flDownload.do?bylClsCd=110202&flSeq=162643591&gubun="
)
OFFICIAL_FOREIGN_TAX_CREDIT_LAW_SOURCE_URL = (
    "https://www.law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1033240233"
)
OFFICIAL_FOREIGN_TAX_CREDIT_ENFORCEMENT_SOURCE_URL = (
    "https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1019675245"
)
OFFICIAL_FOREIGN_TAX_CREDIT_FORM_SOURCE_URL = (
    "https://www.law.go.kr/flDownload.do?bylClsCd=110202&flSeq=160077771&gubun="
)
OFFICIAL_LOCAL_INCOME_TAX_BASE_SOURCE_URL = (
    "https://law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1032059543"
)
OFFICIAL_LOCAL_INCOME_TAX_RATE_SOURCE_URL = (
    "https://law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1026500915"
)
OFFICIAL_LOCAL_FINANCIAL_INCOME_COMPARISON_SOURCE_URL = (
    "https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1027080671"
)
OFFICIAL_LOCAL_INCOME_TAX_RETURN_FORM_SOURCE_URL = (
    "https://www.law.go.kr/LSW/flDownload.do?bylClsCd=110202&flSeq=160799993&gubun="
)
OFFICIAL_LOCAL_DIVIDEND_TAX_CREDIT_LAW_SOURCE_URL = (
    "https://law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1024240555"
)
OFFICIAL_LOCAL_PREPAID_SPECIAL_WITHHOLDING_LAW_SOURCE_URL = (
    "https://law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1029489965"
)
OFFICIAL_LOCAL_SPECIAL_WITHHOLDING_DUTY_SOURCE_URL = (
    "https://www.law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1031061107"
)
OFFICIAL_LOCAL_FOREIGN_TAX_CREDIT_LAW_SOURCE_URL = (
    "https://law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1024234119"
)
OFFICIAL_LOCAL_FOREIGN_TAX_CREDIT_ENFORCEMENT_SOURCE_URL = (
    "https://law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lspttninfSeq=64096"
)
OFFICIAL_LOCAL_INCOME_TAX_GENERAL_CREDIT_LINK_SOURCE_URL = (
    "https://law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1021964939"
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
INTERIM_PREPAID_INCOME_TAX_VERIFIED_ON = "2026-09-27"
FOREIGN_TAX_CREDIT_VERIFIED_ON = "2026-09-27"
LOCAL_INCOME_TAX_COMPARISON_VERIFIED_ON = "2026-09-27"
LOCAL_DIVIDEND_TAX_CREDIT_VERIFIED_ON = "2026-09-27"
LOCAL_PREPAID_SPECIAL_WITHHOLDING_VERIFIED_ON = "2026-09-27"
LOCAL_FOREIGN_TAX_CREDIT_VERIFIED_ON = "2026-09-27"
