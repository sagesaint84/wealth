"""2026 financial-income projection thresholds.

This module intentionally contains only thresholds needed for projection/status
output. Full income-tax, tax-treatment classification, high-dividend special
rules, and health-insurance calculations belong to later Phase 10.5 modules.
"""

RULE_YEAR = 2026

# Product warning threshold. This is not a statutory tax threshold; it is an
# early-warning marker used to surface that annual financial income is moving
# materially closer to the statutory comprehensive-tax threshold.
FINANCIAL_INCOME_WATCH_THRESHOLD_KRW = 10_000_000

# Statutory comprehensive taxation threshold for annual taxable financial
# income (interest + dividend income). Phase 10.5A-1 uses this only as a
# screening marker because the existing record model does not yet classify all
# non-taxable / separately taxed income or the 2026 high-dividend special case.
FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW = 20_000_000

# Official basis verified 2026-09-26:
# 1) 국가법령정보센터, 소득세법 시행규칙 별지 제40호서식(1), 개정 2025-03-21.
#    - 금융소득 종합과세기준금액 20,000,000원
#    - 배당액은 원천징수세액 차감 전 총배당액으로 기재
#    - 비과세/분리과세 이자·배당소득은 작성 대상에서 제외
# 2) 국세청 2026-03-09 안내: 2026년부터 일정 고배당기업 배당소득에
#    별도 분리과세 특례가 도입됨.
OFFICIAL_RULE_SOURCE_URL = (
    "https://law.go.kr/LSW/flDownload.do?bylClsCd=110202&flSeq=151083979&gubun="
)
OFFICIAL_HIGH_DIVIDEND_SOURCE_URL = (
    "https://www.nts.go.kr/nts/na/ntt/selectNttInfo.do?nttSn=1349597"
)
RULE_VERIFIED_ON = "2026-09-26"
