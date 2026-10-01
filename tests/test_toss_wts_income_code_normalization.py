from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.services.toss_wts_income import (
    build_toss_wts_income_fingerprint,
    canonicalize_toss_wts_stock_code,
    map_toss_wts_income_row,
)
from app.services.toss_wts_income_code_migration import migrate_dividend_records_file


def ledger_row(*, market="kr", currency="KRW", stock_code="A091170"):
    return {
        "market": market,
        "category": "cash",
        "currency": currency,
        "datetime": "2026-09-02T12:00:00+09:00",
        "stock_name": "KODEX 은행",
        "amount": 80830,
        "adjusted_amount": 68390,
        "source_meta": {
            "summary_no": "1104" if market == "kr" else "1207",
            "trade_type_name": "배당금입금" if market == "kr" else "",
            "transaction_type_code": "1",
            "transaction_type_name": "입금",
            "stock_code": stock_code,
            "stock_name": "KODEX 은행",
            "product_name": "KODEX 은행",
            "provider_amount": 80830,
            "provider_adjusted_amount": 68390,
            "provider_tax_amount": 12440 if market == "kr" else 0,
            "composite_key": {"date": "20260902", "no": 17},
        },
    }


def test_kr_provider_a_prefix_is_canonicalized_only_for_exact_six_digit_code():
    assert canonicalize_toss_wts_stock_code("kr", "A091170") == "091170"
    assert canonicalize_toss_wts_stock_code("kr", "091170") == "091170"
    assert canonicalize_toss_wts_stock_code("kr", "AABC123") == "AABC123"
    assert canonicalize_toss_wts_stock_code("us", "A091170") == "A091170"


def test_mapper_stores_canonical_code_and_keeps_provider_code_in_metadata():
    row = ledger_row()
    candidate = map_toss_wts_income_row(row)
    assert candidate is not None
    assert candidate["code"] == "091170"
    assert candidate["name"] == "KODEX 은행"
    assert candidate["source_meta"]["provider_stock_code"] == "A091170"
    assert candidate["source_fingerprint"] == build_toss_wts_income_fingerprint(row)


def test_fingerprint_continues_to_use_provider_raw_code():
    prefixed = ledger_row(stock_code="A091170")
    canonical = ledger_row(stock_code="091170")
    assert build_toss_wts_income_fingerprint(prefixed) != build_toss_wts_income_fingerprint(canonical)


def test_migration_dry_run_is_non_destructive_and_apply_is_idempotent():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "dividend_records.json"
        fingerprint = "toss-wts-income:v1:" + "a" * 64
        payload = {
            "records": [
                {
                    "id": "target",
                    "date": "2026-09-02",
                    "code": "A091170",
                    "name": "KODEX 은행",
                    "currency": "KRW",
                    "amount": 68390,
                    "income_type": "distribution",
                    "source": "toss_wts",
                    "source_fingerprint": fingerprint,
                    "source_meta": {"market": "kr", "summary_no": "1117"},
                },
                {
                    "id": "manual",
                    "code": "A091170",
                    "currency": "KRW",
                    "income_type": "distribution",
                    "source": "manual",
                    "source_meta": {"market": "kr"},
                },
                {
                    "id": "foreign",
                    "code": "A091170",
                    "currency": "USD",
                    "income_type": "dividend",
                    "source": "toss_wts",
                    "source_meta": {"market": "us"},
                },
            ],
            "updated_at": "2026-09-30T00:00:00+09:00",
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        dry = migrate_dividend_records_file(path, apply=False)
        assert dry["matched"] == 1
        assert dry["applied"] == 0
        unchanged = json.loads(path.read_text(encoding="utf-8"))
        assert unchanged["records"][0]["code"] == "A091170"

        applied = migrate_dividend_records_file(path, apply=True)
        assert applied["matched"] == 1
        assert applied["applied"] == 1
        migrated = json.loads(path.read_text(encoding="utf-8"))
        target = migrated["records"][0]
        assert target["code"] == "091170"
        assert target["source_fingerprint"] == fingerprint
        assert target["source_meta"]["provider_stock_code"] == "A091170"
        assert migrated["records"][1]["code"] == "A091170"
        assert migrated["records"][2]["code"] == "A091170"

        second = migrate_dividend_records_file(path, apply=True)
        assert second["matched"] == 0
        assert second["applied"] == 0
