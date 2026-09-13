from datetime import date
from decimal import Decimal
import unittest

from data_pipeline.collectors.meta_ads import collect_meta_daily
from data_pipeline.settings import AccountMapping


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeMetaClient:
    def __init__(self, pages: list[dict]) -> None:
        self.pages = list(pages)
        self.calls: list[dict] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return FakeResponse(self.pages.pop(0))


class MetaCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mapping = AccountMapping(
            brand_slug="samla",
            platform="meta_ads",
            external_account_id="act_123",
            display_name="SAMLA Meta",
            currency="SAR",
        )

    def test_collects_daily_campaign_rows_and_paginates(self) -> None:
        client = FakeMetaClient(
            [
                {
                    "data": [
                        {
                            "campaign_id": "campaign-1",
                            "campaign_name": "Wishlist traffic",
                            "date_start": "2026-07-01",
                            "spend": "375",
                            "impressions": "1000",
                            "clicks": "50",
                            "actions": [
                                {"action_type": "lead", "value": "4"},
                                {"action_type": "purchase", "value": "2"},
                            ],
                            "action_values": [
                                {"action_type": "purchase", "value": "750"}
                            ],
                        }
                    ],
                    "paging": {
                        "next": "https://graph.facebook.com/next-page?after=abc&access_token=secret"
                    },
                },
                {"data": [], "paging": {}},
            ]
        )
        records = collect_meta_daily(
            self.mapping,
            access_token="test-token",
            api_version="v99.0",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
            client=client,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(records[0].spend_usd, Decimal("100.000000"))
        self.assertEqual(records[0].conversion_value_usd, Decimal("200.000000"))
        self.assertEqual(records[0].leads, 4)
        self.assertEqual(records[0].conversions, Decimal("2"))
        first_params = client.calls[0]["params"]
        self.assertEqual(first_params["time_increment"], 1)
        self.assertEqual(first_params["level"], "campaign")
        self.assertNotIn("access_token", first_params)
        self.assertNotIn("access_token", client.calls[1]["url"])
        self.assertEqual(
            client.calls[0]["headers"]["Authorization"], "Bearer test-token"
        )
        self.assertIsNone(client.calls[1]["params"])

    def test_requires_explicit_api_version(self) -> None:
        with self.assertRaisesRegex(ValueError, "form vNN.N"):
            collect_meta_daily(
                self.mapping,
                access_token="test-token",
                api_version="latest",
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 1),
                client=FakeMetaClient([]),
            )


if __name__ == "__main__":
    unittest.main()
