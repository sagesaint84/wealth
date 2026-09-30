import unittest


class DartParserAccuracyImportTests(unittest.TestCase):
    def test_public_parser_symbol_uses_accuracy_adapter(self):
        from app.services.ipo.dart_parser import DartSemanticParser

        self.assertEqual(DartSemanticParser.__name__, "AccurateDartSemanticParser")
        self.assertEqual(DartSemanticParser.__module__, "app.services.ipo.dart_parser_accuracy")


if __name__ == "__main__":
    unittest.main()
