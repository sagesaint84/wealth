"""Wealth IPO subsystem package."""

# Install the filing-layout accuracy adapter before callers import
# ``app.services.ipo.dart_parser.DartSemanticParser``. The base parser remains
# available as the implementation fallback for unaffected extraction methods.
from app.services.ipo import dart_parser as _dart_parser
from app.services.ipo.dart_parser_accuracy import AccurateDartSemanticParser

_dart_parser.DartSemanticParser = AccurateDartSemanticParser
