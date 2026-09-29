import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data_pipeline.settings import accounts_for_platform, load_account_mappings


class AccountMappingTests(unittest.TestCase):
    def write_config(self, directory: str, payload: dict) -> Path:
        path = Path(directory) / "mapping.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_loads_and_normalizes_accounts(self) -> None:
        with TemporaryDirectory() as directory:
            path = self.write_config(
                directory,
                {
                    "accounts": [
                        {
                            "brand_slug": "SAMLA",
                            "platform": "META_ADS",
                            "external_account_id": "act_123",
                            "display_name": "SAMLA Meta",
                            "currency": "sar",
                        },
                        {
                            "brand_slug": "jackaroo-strike",
                            "platform": "google_ads",
                            "external_account_id": "456",
                            "display_name": "Jackaroo Google",
                            "currency": "USD",
                        },
                    ]
                },
            )
            mappings = load_account_mappings(path)

        self.assertEqual(mappings[0].brand_slug, "samla")
        self.assertEqual(mappings[0].currency, "SAR")
        self.assertEqual(len(accounts_for_platform(mappings, "meta_ads")), 1)

    def test_rejects_duplicate_platform_account(self) -> None:
        duplicate = {
            "brand_slug": "samla",
            "platform": "meta_ads",
            "external_account_id": "act_123",
            "display_name": "Meta",
            "currency": "USD",
        }
        with TemporaryDirectory() as directory:
            path = self.write_config(directory, {"accounts": [duplicate, duplicate]})
            with self.assertRaisesRegex(ValueError, "duplicate account mapping"):
                load_account_mappings(path)

