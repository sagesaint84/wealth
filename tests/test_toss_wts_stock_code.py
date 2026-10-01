from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.services.toss_wts_income import map_toss_wts_income_row
from app.services.toss_wts_income_code_migration import migrate_dividend_records_file


def test_income_mapper_supports_alphanumeric_korean_short_code():
    row = {
        "market": "kr",
        "currency": "KRW",
        "datetime": "2026-09-02T12:00:00+09:00",
        "adjusted_amount": 68390,
        "stock_name": "가상 알파코드 ETF",
        "source_meta": {
            "summary_no": "1117",
            "trade_type_name": "결산분배금입금",
            "transaction_type_code": "1",
            "transaction_type_name": "입금",
            "stock_code": "A0193T0",
            "stock_name": "가상 알파코드 ETF",
            "product_name": "가상 알파코드 ETF",
            "provider_amount": 80830,
            "provider_tax_amount": 12440,
            "composite_key": {"date": "20260902", "no": 31},
        },
    }
    candidate = map_toss_wts_income_row(row)
    assert candidate is not None
    assert candidate["code"] == "0193T0"
    assert candidate["source_meta"]["provider_stock_code"] == "A0193T0"


def test_income_migration_supports_alphanumeric_code_without_touching_fingerprint():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "dividend_records.json"
        fingerprint = "toss-wts-income:v1:" + "b" * 64
        payload = {
            "records": [
                {
                    "code": "A0193T0",
                    "currency": "KRW",
                    "income_type": "distribution",
                    "source": "toss_wts",
                    "source_fingerprint": fingerprint,
                    "source_meta": {"market": "kr"},
                }
            ],
            "updated_at": "2026-10-01T00:00:00+09:00",
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        dry = migrate_dividend_records_file(path, apply=False)
        assert dry["matched"] == 1
        assert dry["applied"] == 0

        applied = migrate_dividend_records_file(path, apply=True)
        assert applied["applied"] == 1
        migrated = json.loads(path.read_text(encoding="utf-8"))["records"][0]
        assert migrated["code"] == "0193T0"
        assert migrated["source_meta"]["provider_stock_code"] == "A0193T0"
        assert migrated["source_fingerprint"] == fingerprint
