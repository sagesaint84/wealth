"""Wealth IPO subsystem package."""

from __future__ import annotations

import os

# Install the filing-layout accuracy adapter before callers import
# ``app.services.ipo.dart_parser.DartSemanticParser``. The base parser remains
# available as the implementation fallback for unaffected extraction methods.
from app.services.ipo import dart_parser as _dart_parser
from app.services.ipo.dart_parser_accuracy import AccurateDartSemanticParser

_dart_parser.DartSemanticParser = AccurateDartSemanticParser

# Keep the public orchestrator API stable while separating interactive and
# scheduled work. The interactive UI refresh must stay on the original
# market-only KIS/NAVER-progress path; expensive discovery/DART enrichment is
# reserved for the scheduled/full refresh path.
from app.services.ipo import orchestrator as _orchestrator
from app.services.ipo.refresh_adapter import (
    _BASE_REFRESH_MARKET as _refresh_ipo_market,
    refresh_ipo_market_enriched as _refresh_ipo_market_enriched,
)

_orchestrator.refresh_ipo_market = _refresh_ipo_market
_orchestrator.refresh_ipo_market_enriched = _refresh_ipo_market_enriched

# KRX Data Marketplace historical data now requires an authenticated session.
# Wire the explicit historical-sync service to the authenticated client without
# affecting routine market refreshes or other KRX helpers.
from app.services.ipo import historical_online_sync as _historical_online_sync
from app.services.ipo.krx_authenticated_client import AuthenticatedKrxHistoricalClient

_original_online_historical_preview = _historical_online_sync.create_online_historical_preview


def _authenticated_online_historical_preview(*args, **kwargs):
    # Tests and controlled callers may inject a fake/source-specific client.
    if kwargs.get("krx_client") is None:
        if not (os.getenv("KRX_ID", "").strip() and os.getenv("KRX_PW", "").strip()):
            raise _historical_online_sync.HistoricalOnlineSyncError(
                "KRX_AUTH_REQUIRED",
                "KRX 전체 과거자료 조회에는 KRX Data Marketplace 로그인 정보가 필요합니다. "
                "서버에 KRX_ID와 KRX_PW를 설정한 뒤 다시 시도해 주세요.",
            )
    return _original_online_historical_preview(*args, **kwargs)


_historical_online_sync.KrxClient = AuthenticatedKrxHistoricalClient
_historical_online_sync.create_online_historical_preview = _authenticated_online_historical_preview
