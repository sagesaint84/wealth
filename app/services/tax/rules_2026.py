"""2026 financial-income projection thresholds.

This module intentionally contains only thresholds needed for projection/status
output. Full income-tax and health-insurance calculations belong to later
Phase 10.5 rule modules.
"""

RULE_YEAR = 2026

# Product warning threshold. This is not a statutory tax threshold; it is an
# early-warning marker used to surface that annual financial income is moving
# materially closer to the statutory comprehensive-tax threshold.
FINANCIAL_INCOME_WATCH_THRESHOLD_KRW = 10_000_000

# Statutory comprehensive taxation threshold for annual taxable financial
# income (interest + dividend income), used here only as a projection marker.
# Official basis verified 2026-09-26:
# 대한민국 법제처 국가법령정보센터, 소득세법 시행규칙 별지 제40호서식(1)
# "종합소득산출세액계산서(금융소득자용)" — 종합과세기준금액 20,000,000원.
FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW = 20_000_000
OFFICIAL_SOURCE_URL = (
    "https://law.go.kr/LSW/flDownload.do?bylClsCd=110202&flSeq=151083979&gubun="
)
RULE_VERIFIED_ON = "2026-09-26"
