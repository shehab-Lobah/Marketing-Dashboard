"""Canonical records shared by all advertising-platform collectors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .currency import amount_to_usd, currency_code


@dataclass(frozen=True, slots=True)
class DailyCampaignMetric:
    """One brand, platform, account, campaign and calendar day."""

    brand_slug: str
    platform: str
    external_account_id: str
    external_campaign_id: str
    campaign_name: str
    metric_date: date
    spend_original: Decimal
    original_currency: str
    fx_to_usd: Decimal
    spend_usd: Decimal
    impressions: int = 0
    clicks: int = 0
    conversions: Decimal = Decimal("0")
    conversion_value_usd: Decimal = Decimal("0")
    installs: int = 0
    leads: int = 0

    @classmethod
    def build(
        cls,
        *,
        brand_slug: str,
        platform: str,
        external_account_id: str,
        external_campaign_id: str,
        campaign_name: str,
        metric_date: date,
        spend_original: Decimal | float | int | str,
        original_currency: str,
        fx_rates: dict[str, Decimal | float | str] | None = None,
        impressions: int = 0,
        clicks: int = 0,
        conversions: Decimal | float | int | str = 0,
        conversion_value_usd: Decimal | float | int | str = 0,
        installs: int = 0,
        leads: int = 0,
    ) -> "DailyCampaignMetric":
        amount = Decimal(str(spend_original))
        spend_usd, rate = amount_to_usd(amount, original_currency, fx_rates)
        record = cls(
            brand_slug=brand_slug.strip().lower(),
            platform=platform.strip().lower(),
            external_account_id=external_account_id.strip(),
            external_campaign_id=external_campaign_id.strip(),
            campaign_name=campaign_name.strip(),
            metric_date=metric_date,
            spend_original=amount,
            original_currency=currency_code(original_currency),
            fx_to_usd=rate,
            spend_usd=spend_usd,
            impressions=int(impressions),
            clicks=int(clicks),
            conversions=Decimal(str(conversions)),
            conversion_value_usd=Decimal(str(conversion_value_usd)),
            installs=int(installs),
            leads=int(leads),
        )
        record.validate()
        return record

    def validate(self) -> None:
        required = {
            "brand_slug": self.brand_slug,
            "platform": self.platform,
            "external_account_id": self.external_account_id,
            "external_campaign_id": self.external_campaign_id,
            "campaign_name": self.campaign_name,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")
        numeric = {
            "spend_original": self.spend_original,
            "spend_usd": self.spend_usd,
            "impressions": self.impressions,
            "clicks": self.clicks,
            "conversions": self.conversions,
            "conversion_value_usd": self.conversion_value_usd,
            "installs": self.installs,
            "leads": self.leads,
        }
        negative = [name for name, value in numeric.items() if value < 0]
        if negative:
            raise ValueError(f"Negative metrics are not allowed: {', '.join(negative)}")
    @property
    def ctr(self) -> Decimal | None:
        return Decimal(self.clicks) / Decimal(self.impressions) if self.impressions else None

    @property
    def cpc_usd(self) -> Decimal | None:
        return self.spend_usd / Decimal(self.clicks) if self.clicks else None

    def to_ingest_row(self) -> dict[str, object]:
        """Return the normalized payload consumed by the database writer.

        The writer resolves ``brand_slug`` and ``external_account_id`` to their
        database UUIDs before upserting the campaign metric.
        """
        return {
            "brand_slug": self.brand_slug,
            "platform": self.platform,
            "external_account_id": self.external_account_id,
            "external_campaign_id": self.external_campaign_id,
            "campaign_name": self.campaign_name,
            "metric_date": self.metric_date.isoformat(),
            "spend_original": str(self.spend_original),
            "original_currency": self.original_currency,
            "fx_to_usd": str(self.fx_to_usd),
            "spend_usd": str(self.spend_usd),
            "impressions": self.impressions,
            "clicks": self.clicks,
            "conversions": str(self.conversions),
            "conversion_value_usd": str(self.conversion_value_usd),
            "installs": self.installs,
            "leads": self.leads,
        }
