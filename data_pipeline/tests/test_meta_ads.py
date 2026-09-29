from datetime import date
from decimal import Decimal
import unittest

from data_pipeline.collectors.meta_ads import (
    collect_meta_ad_daily,
    collect_meta_ads_catalog,
    collect_meta_daily,
    discover_meta_ad_accounts,
)
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

    def test_collects_every_ad_with_web_and_app_metrics(self) -> None:
        client = FakeMetaClient(
            [
                {
                    "data": [
                        {
                            "campaign_id": "campaign-1",
                            "campaign_name": "Launch",
                            "adset_id": "adset-1",
                            "adset_name": "GCC",
                            "ad_id": "ad-1",
                            "ad_name": "Gameplay",
                            "date_start": "2026-07-01",
                            "spend": "375",
                            "impressions": "1000",
                            "reach": "800",
                            "clicks": "50",
                            "inline_link_clicks": "40",
                            "actions": [
                                {"action_type": "landing_page_view", "value": "25"},
                                {"action_type": "mobile_app_install", "value": "5"},
                            ],
                        }
                    ]
                }
            ]
        )

        records = collect_meta_ad_daily(
            self.mapping,
            access_token="test-token",
            api_version="v99.0",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            client=client,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].external_ad_id, "ad-1")
        self.assertEqual(records[0].reach, 800)
        self.assertEqual(records[0].link_clicks, 40)
        self.assertEqual(records[0].landing_page_views, 25)
        self.assertEqual(records[0].installs, 5)
        self.assertEqual(client.calls[0]["params"]["level"], "ad")

    def test_collects_ads_with_no_delivery_from_catalog(self) -> None:
        client = FakeMetaClient(
            [
                {
                    "data": [
                        {
                            "id": "ad-1",
                            "name": "Never delivered",
                            "status": "PAUSED",
                            "effective_status": "PAUSED",
                            "created_time": "2025-12-14T17:44:18+0300",
                            "updated_time": "2026-01-01T09:00:00+0300",
                            "campaign": {"id": "campaign-1", "name": "Launch"},
                            "adset": {"id": "adset-1", "name": "GCC"},
                            "creative": {"id": "creative-1"},
                        }
                    ]
                }
            ]
        )

        records = collect_meta_ads_catalog(
            self.mapping,
            access_token="test-token",
            api_version="v99.0",
            client=client,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].external_ad_id, "ad-1")
        self.assertEqual(records[0].creative_id, "creative-1")
        self.assertEqual(records[0].status, "PAUSED")
        self.assertTrue(client.calls[0]["url"].endswith("/act_123/ads"))

    def test_discovers_accounts_and_strips_token_from_pagination(self) -> None:
        client = FakeMetaClient(
            [
                {
                    "data": [
                        {
                            "id": "act_123",
                            "name": "SAMLA",
                            "currency": "sar",
                            "account_status": 1,
                        }
                    ],
                    "paging": {
                        "next": "https://graph.facebook.com/next?after=abc&access_token=secret"
                    },
                },
                {
                    "data": [
                        {
                            "id": "act_456",
                            "name": "Jackaroo Strike",
                            "currency": "USD",
                        }
                    ]
                },
            ]
        )

        accounts = discover_meta_ad_accounts(
            access_token="test-token",
            api_version="v99.0",
            client=client,
        )

        self.assertEqual([item["external_account_id"] for item in accounts], ["act_123", "act_456"])
        self.assertEqual(accounts[0]["currency"], "SAR")
        self.assertEqual(accounts[0]["account_status"], "1")
        self.assertNotIn("access_token", client.calls[1]["url"])
        self.assertEqual(
            client.calls[0]["headers"]["Authorization"], "Bearer test-token"
        )


if __name__ == "__main__":
    unittest.main()
