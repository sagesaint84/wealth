from datetime import date

from app.services.ipo.source_discovery import (
    _promote_verified_market,
    _promote_verified_markets,
)


def _sources(naver_market="KOSDAQ", krx_market="KSQ"):
    return {
        "naver": {
            "market_type": naver_market,
            "observed_at": "2026-10-02T19:22:19+09:00",
        },
        "krx": {
            "market_code": krx_market,
            "observed_at": "2026-10-02T19:22:19+09:00",
        },
    }


def test_promotes_blank_market_from_naver_krx_consensus():
    ipo = {
        "market": None,
        "sources": _sources(),
    }

    assert _promote_verified_market(ipo) is True
    assert ipo["market"] == "KOSDAQ"
    assert (
        ipo["sources"]["market_confirmation"]["source"]
        == "stored_naver_krx_consensus"
    )


def test_preserves_existing_canonical_market():
    ipo = {
        "market": "KOSPI",
        "sources": _sources(),
    }

    assert _promote_verified_market(ipo) is False
    assert ipo["market"] == "KOSPI"
    assert "market_confirmation" not in ipo["sources"]


def test_requires_two_source_consensus():
    mismatch = {
        "market": None,
        "sources": _sources("KOSDAQ", "STK"),
    }
    missing_krx = {
        "market": None,
        "sources": {
            "naver": {"market_type": "KOSDAQ"},
        },
    }

    assert _promote_verified_market(mismatch) is False
    assert mismatch["market"] is None

    assert _promote_verified_market(missing_krx) is False
    assert missing_krx["market"] is None


def test_bounded_promotion_only_touches_window_records():
    market = {
        "ipos": [
            {
                "ipo_id": "sep",
                "company_name": "sep",
                "market": None,
                "actual_listing_date": "2026-09-22",
                "sources": _sources(),
            },
            {
                "ipo_id": "old",
                "company_name": "old",
                "market": None,
                "actual_listing_date": "2025-09-22",
                "sources": _sources(),
            },
        ],
    }

    promoted = _promote_verified_markets(
        market,
        start=date(2026, 9, 1),
        end=date(2026, 11, 30),
    )

    assert promoted == 1
    assert market["ipos"][0]["market"] == "KOSDAQ"
    assert market["ipos"][1]["market"] is None


def test_kospi_alias_consensus_is_supported():
    ipo = {
        "market": None,
        "sources": _sources("KOSPI", "STK"),
    }

    assert _promote_verified_market(ipo) is True
    assert ipo["market"] == "KOSPI"
