from datetime import date
from decimal import Decimal
import unittest

from data_pipeline.models import DailyCampaignMetric
from data_pipeline.settings import AccountMapping
from data_pipeline.supabase_writer import SupabaseWriter


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        if url.endswith("/brands"):
            return FakeResponse([{"id": "brand-uuid"}])
        if url.endswith("/ad_accounts"):
            return FakeResponse([{"id": "account-uuid"}])
        return FakeResponse(None)


class SupabaseWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = FakeSession()
        self.writer = SupabaseWriter(
            "https://example.supabase.co",
            "test-service-role-key",
            session=self.session,
        )
        self.mapping = AccountMapping(
            brand_slug="samla",
            platform="meta_ads",
            external_account_id="act_test",
            display_name="SAMLA Meta",
            currency="SAR",
        )

    def test_upserts_resolved_daily_record(self) -> None:
        record = DailyCampaignMetric.build(
            brand_slug="samla",
            platform="meta_ads",
            external_account_id="act_test",
            external_campaign_id="campaign_test",
            campaign_name="Wishlist",
            metric_date=date(2026, 7, 1),
            spend_original=Decimal("375"),
            original_currency="SAR",
            impressions=1000,
            clicks=50,
        )
        count = self.writer.upsert_campaign_metrics([record], [self.mapping])

        self.assertEqual(count, 1)
        metric_call = self.session.calls[-1]
        row = metric_call["json"][0]
        self.assertEqual(row["brand_id"], "brand-uuid")
        self.assertEqual(row["ad_account_id"], "account-uuid")
        self.assertEqual(row["spend_usd"], "100.000000")
        self.assertNotIn("brand_slug", row)

    def test_rejects_unmapped_account(self) -> None:
        record = DailyCampaignMetric.build(
            brand_slug="samla",
            platform="google_ads",
            external_account_id="unmapped",
            external_campaign_id="campaign_test",
            campaign_name="Search",
            metric_date=date(2026, 7, 1),
            spend_original=1,
            original_currency="USD",
        )
        with self.assertRaisesRegex(ValueError, "No brand mapping"):
            self.writer.upsert_campaign_metrics([record], [self.mapping])


if __name__ == "__main__":
    unittest.main()
