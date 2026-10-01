from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from itsdangerous import URLSafeTimedSerializer

from app.services.toss_wts_feed import (
    get_verified_realized_feed_provider_product_code,
    project_realized_feed_row,
    sign_realized_feed_row,
    verify_realized_feed_row_token,
)
from app.services.toss_wts_realized import (
    build_toss_wts_realized_fingerprint,
    map_toss_wts_profit_row,
)
from app.services.toss_wts_realized_code_migration import migrate_realized_records_file
from app.services.toss_wts_stock_code import canonicalize_toss_wts_stock_code


def profit_row(*, market_type="kr", product_code="A0193T0"):
    return {
        "date": "2026-09-22",
        "market_type": market_type,
        "symbol": "0193T0" if market_type == "kr" else "AAPL",
        "product_code": product_code,
        "name": "KODEX SK하이닉스단일종목레버리지" if market_type == "kr" else "Apple",
        "quantity": 100,
        "profit_loss": {"krw": 214652, "usd": 156.0 if market_type == "us" else None},
        "profit_rate": 21.93,
        "sell_amount": {"krw": 1193500, "usd": 900.0 if market_type == "us" else None},
        "buy_amount": {"krw": 978523, "usd": 744.0 if market_type == "us" else None},
    }


def map_row(row, *, provider_product_code=None):
    return map_toss_wts_profit_row(
        row,
        account_name="토스증권",
        source_account_scope="unverified",
        owner="모두",
        profit_rate_basis="KRW",
        fetched_at="2026-10-01T22:30:00+09:00",
        provider_product_code=provider_product_code,
    )


def test_kr_provider_a_prefix_supports_numeric_and_alphanumeric_short_codes():
    assert canonicalize_toss_wts_stock_code("kr", "A102970") == "102970"
    assert canonicalize_toss_wts_stock_code("kr", "A091160") == "091160"
    assert canonicalize_toss_wts_stock_code("kr", "A0193T0") == "0193T0"
    assert canonicalize_toss_wts_stock_code("kr", "A0193W0") == "0193W0"
    assert canonicalize_toss_wts_stock_code("kr", "0193T0") == "0193T0"
    assert canonicalize_toss_wts_stock_code("us", "A0193T0") == "A0193T0"
    assert canonicalize_toss_wts_stock_code("kr", "A12345") == "A12345"
    assert canonicalize_toss_wts_stock_code("kr", "A0193t0") == "A0193t0"


def test_read_only_feed_projects_canonical_code_without_mutating_provider_row():
    row = profit_row(product_code="A0193W0")
    original = copy.deepcopy(row)
    projected = project_realized_feed_row(row)
    assert projected["product_code"] == "0193W0"
    assert row == original

    us_row = profit_row(market_type="us", product_code="A0193W0")
    assert project_realized_feed_row(us_row)["product_code"] == "A0193W0"


def test_signed_feed_token_binds_canonical_display_row_and_preserves_raw_provider_code():
    raw = profit_row(product_code="A0193T0")
    display = project_realized_feed_row(raw)
    serializer = URLSafeTimedSerializer("unit-test-secret")

    with patch("app.services.toss_wts_feed._get_serializer", return_value=serializer):
        token = sign_realized_feed_row(
            display,
            user_id="user-1",
            generation_id="generation-1",
            provider_product_code=raw["product_code"],
        )
        valid, error = verify_realized_feed_row_token(
            display, token, user_id="user-1", current_generation_id="generation-1"
        )
        assert valid is True
        assert error is None
        provider_code, error = get_verified_realized_feed_provider_product_code(
            display, token, user_id="user-1", current_generation_id="generation-1"
        )
        assert provider_code == "A0193T0"
        assert error is None

        tampered = dict(display, product_code="0193W0")
        valid, error = verify_realized_feed_row_token(
            tampered, token, user_id="user-1", current_generation_id="generation-1"
        )
        assert valid is False
        assert error == "ROW_TAMPERED"


def test_mapper_uses_canonical_wealth_code_but_raw_provider_code_for_fingerprint_identity():
    raw = profit_row(product_code="A0193T0")
    candidate = map_row(raw)
    assert candidate["code"] == "0193T0"
    assert candidate["source_meta"]["product_code"] == "A0193T0"

    fingerprint = build_toss_wts_realized_fingerprint(candidate)
    canonical_meta = copy.deepcopy(candidate)
    canonical_meta["source_meta"]["product_code"] = "0193T0"
    assert build_toss_wts_realized_fingerprint(canonical_meta) != fingerprint

    display = project_realized_feed_row(raw)
    from_display = map_row(display, provider_product_code="A0193T0")
    assert from_display["code"] == "0193T0"
    assert from_display["source_meta"]["product_code"] == "A0193T0"
    assert build_toss_wts_realized_fingerprint(from_display) == fingerprint


def test_realized_migration_dry_run_apply_and_idempotency_preserve_provider_identity():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "realized_pnl_records.json"
        fingerprint = "toss-wts-realized:v1:" + "a" * 64
        payload = {
            "records": [
                {
                    "id": "numeric",
                    "date": "2026-09-22",
                    "code": "A102970",
                    "name": "KODEX 증권",
                    "currency": "KRW",
                    "source": "toss_wts",
                    "source_fingerprint": fingerprint,
                    "source_meta": {"market_type": "kr", "product_code": "A102970"},
                },
                {
                    "id": "alpha",
                    "date": "2026-09-22",
                    "code": "A0193T0",
                    "name": "KODEX SK하이닉스단일종목레버리지",
                    "currency": "KRW",
                    "source": "toss_wts",
                    "source_fingerprint": fingerprint,
                    "source_meta": {"market_type": "kr", "product_code": "A0193T0"},
                },
                {
                    "id": "manual",
                    "code": "A091160",
                    "currency": "KRW",
                    "source": "manual",
                    "source_meta": {"market_type": "kr", "product_code": "A091160"},
                },
                {
                    "id": "foreign",
                    "code": "A0193T0",
                    "currency": "USD",
                    "source": "toss_wts",
                    "source_meta": {"market_type": "us", "product_code": "A0193T0"},
                },
                {
                    "id": "mismatch",
                    "code": "A091160",
                    "currency": "KRW",
                    "source": "toss_wts",
                    "source_meta": {"market_type": "kr", "product_code": "A999999"},
                },
            ],
            "updated_at": "2026-10-01T00:00:00+09:00",
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        dry = migrate_realized_records_file(path, apply=False)
        assert dry["matched"] == 2
        assert dry["applied"] == 0
        unchanged = json.loads(path.read_text(encoding="utf-8"))
        assert unchanged["records"][0]["code"] == "A102970"
        assert unchanged["records"][1]["code"] == "A0193T0"

        applied = migrate_realized_records_file(path, apply=True)
        assert applied["matched"] == 2
        assert applied["applied"] == 2
        migrated = json.loads(path.read_text(encoding="utf-8"))
        assert migrated["records"][0]["code"] == "102970"
        assert migrated["records"][1]["code"] == "0193T0"
        assert migrated["records"][0]["source_fingerprint"] == fingerprint
        assert migrated["records"][0]["source_meta"]["product_code"] == "A102970"
        assert migrated["records"][1]["source_meta"]["product_code"] == "A0193T0"
        assert migrated["records"][2]["code"] == "A091160"
        assert migrated["records"][3]["code"] == "A0193T0"
        assert migrated["records"][4]["code"] == "A091160"

        second = migrate_realized_records_file(path, apply=True)
        assert second["matched"] == 0
        assert second["applied"] == 0
