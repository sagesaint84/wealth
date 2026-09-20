import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.services import broker_registry


EXPECTED_IDS = {
    "kis", "nh", "kiwoom", "kb", "toss", "mirae", "samsung", "hana",
    "shinhan", "daishin", "yuanta", "sk", "eugene", "db", "ibk", "kyobo",
    "hyundai", "ls", "im", "bnk",
}


class BrokerRegistryTests(unittest.TestCase):
    def setUp(self):
        broker_registry._load_registry.cache_clear()
        self.addCleanup(broker_registry._load_registry.cache_clear)

    def test_registry_has_exactly_twenty_unique_canonical_brokers(self):
        brokers, aliases = broker_registry._load_registry()
        self.assertEqual(set(brokers), EXPECTED_IDS)
        self.assertEqual(len(brokers), 20)
        self.assertEqual(len({broker["broker_id"] for broker in brokers.values()}), 20)
        self.assertEqual(len(aliases), len(set(aliases)))

    def test_normalization_is_explicit_case_and_whitespace_tolerant(self):
        cases = {
            "한국투자증권": "kis", " 한투 ": "kis", "KIS": "kis",
            "NAMUH": "nh", "영웅문": "kiwoom", "현대증권": "kb",
            "미래에셋대우": "mirae", "HMC투자증권": "hyundai",
            "이베스트투자증권": "ls", "하이투자증권": "im",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(broker_registry.normalize_broker(raw), expected)
                self.assertTrue(broker_registry.is_known_broker(raw))

        for unknown in (None, "", "  ", "한국투자", "미래", "random broker"):
            with self.subTest(unknown=unknown):
                self.assertIsNone(broker_registry.normalize_broker(unknown))
                self.assertFalse(broker_registry.is_known_broker(unknown))

    def test_lookup_returns_copies_and_preserves_canonical_display_name(self):
        kis = broker_registry.get_broker("kis")
        self.assertEqual(kis["display_name"], "한국투자증권")
        self.assertIn("한투", broker_registry.get_aliases("kis"))
        kis["aliases"].append("mutated")
        self.assertNotIn("mutated", broker_registry.get_aliases("kis"))
        self.assertEqual(broker_registry.get_display_name("nh"), "NH투자증권")
        self.assertIsNone(broker_registry.get_broker("not-a-broker"))

    def test_loader_rejects_duplicate_broker_ids_and_alias_collisions(self):
        payload = {
            "brokers": [
                {"broker_id": "one", "display_name": "One", "aliases": ["shared"]},
                {"broker_id": "two", "display_name": "Two", "aliases": ["shared"]},
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(broker_registry, "_REGISTRY_PATH", path):
                broker_registry._load_registry.cache_clear()
                with self.assertRaisesRegex(RuntimeError, "aliases collide"):
                    broker_registry._load_registry()

        payload["brokers"][1]["aliases"] = ["two"]
        payload["brokers"][1]["broker_id"] = "one"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(broker_registry, "_REGISTRY_PATH", path):
                broker_registry._load_registry.cache_clear()
                with self.assertRaisesRegex(RuntimeError, "duplicates broker_id"):
                    broker_registry._load_registry()

    def test_loader_rejects_non_string_aliases(self):
        for malformed_alias in (123, True, None, {"alias": "KIS"}, ["KIS"]):
            with self.subTest(malformed_alias=malformed_alias):
                payload = {
                    "brokers": [
                        {"broker_id": "one", "display_name": "One", "aliases": [malformed_alias]},
                    ]
                }
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "registry.json"
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with patch.object(broker_registry, "_REGISTRY_PATH", path):
                        broker_registry._load_registry.cache_clear()
                        with self.assertRaisesRegex(RuntimeError, "aliases must be strings"):
                            broker_registry._load_registry()

    def test_loader_rejects_duplicate_display_names(self):
        payload = {
            "brokers": [
                {"broker_id": "broker_a", "display_name": "테스트증권", "aliases": []},
                {"broker_id": "broker_b", "display_name": "테스트증권", "aliases": []},
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(broker_registry, "_REGISTRY_PATH", path):
                broker_registry._load_registry.cache_clear()
                with self.assertRaisesRegex(RuntimeError, "duplicates display_name"):
                    broker_registry._load_registry()
