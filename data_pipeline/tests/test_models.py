from datetime import date
from decimal import Decimal
import unittest

from data_pipeline.models import DailyCampaignMetric


class DailyCampaignMetricTests(unittest.TestCase):
    def test_builds_daily_campaign_row_in_usd(self) -> None:
        row = DailyCampaignMetric.build(
            brand_slug="SAMLA",
            platform="meta_ads",
            external_account_id="act_test",
            external_campaign_id="campaign_test",
            campaign_name="Wishlist traffic",
            metric_date=date(2026, 7, 1),
            spend_original="375",
            original_currency="SAR",
            impressions=1000,
            clicks=40,
            conversions=3,
        )

        self.assertEqual(row.brand_slug, "samla")
        self.assertEqual(row.spend_usd, Decimal("100.000000"))
        self.assertEqual(row.ctr, Decimal("0.04"))
        self.assertEqual(row.to_ingest_row()["metric_date"], "2026-07-01")

    def test_rejects_negative_metric(self) -> None:
        with self.assertRaisesRegex(ValueError, "Negative metrics"):
            DailyCampaignMetric.build(
                brand_slug="jackaroo-strike",
                platform="tiktok_ads",
                external_account_id="account_test",
                external_campaign_id="campaign_test",
                campaign_name="Install campaign",
                metric_date=date(2026, 7, 1),
                spend_original=10,
                original_currency="USD",
                impressions=-1,
                clicks=0,
            )


if __name__ == "__main__":
    unittest.main()
