"""Wealth IPO subsystem package."""

# Install the filing-layout accuracy adapter before callers import
# ``app.services.ipo.dart_parser.DartSemanticParser``. The base parser remains
# available as the implementation fallback for unaffected extraction methods.
from app.services.ipo import dart_parser as _dart_parser
from app.services.ipo.dart_parser_accuracy import AccurateDartSemanticParser

_dart_parser.DartSemanticParser = AccurateDartSemanticParser

# Keep the public orchestrator API stable while upgrading source discovery.
# The adapter captures the original functions before these assignments, so the
# scheduled/full and interactive/light paths can reuse the proven base pipeline.
from app.services.ipo import orchestrator as _orchestrator
from app.services.ipo.refresh_adapter import (
    refresh_ipo_market as _refresh_ipo_market,
    refresh_ipo_market_enriched as _refresh_ipo_market_enriched,
)

_orchestrator.refresh_ipo_market = _refresh_ipo_market
_orchestrator.refresh_ipo_market_enriched = _refresh_ipo_market_enriched
