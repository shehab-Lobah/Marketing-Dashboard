"""Canonical records shared by all advertising-platform collectors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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
    reach: int = 0
    clicks: int = 0
    link_clicks: int = 0
    landing_page_views: int = 0
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
        reach: int = 0,
        clicks: int = 0,
        link_clicks: int = 0,
        landing_page_views: int = 0,
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
            reach=int(reach),
            clicks=int(clicks),
            link_clicks=int(link_clicks),
            landing_page_views=int(landing_page_views),
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
            "reach": self.reach,
            "clicks": self.clicks,
            "link_clicks": self.link_clicks,
            "landing_page_views": self.landing_page_views,
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
            "reach": self.reach,
            "clicks": self.clicks,
            "link_clicks": self.link_clicks,
            "landing_page_views": self.landing_page_views,
            "conversions": str(self.conversions),
            "conversion_value_usd": str(self.conversion_value_usd),
            "installs": self.installs,
            "leads": self.leads,
        }


@dataclass(frozen=True, slots=True)
class DailyAdMetric:
    """One brand, platform, account, ad and calendar day."""

    brand_slug: str
    platform: str
    external_account_id: str
    external_campaign_id: str
    campaign_name: str
    external_adset_id: str
    adset_name: str
    external_ad_id: str
    ad_name: str
    metric_date: date
    spend_original: Decimal
    original_currency: str
    fx_to_usd: Decimal
    spend_usd: Decimal
    impressions: int = 0
    reach: int = 0
    clicks: int = 0
    link_clicks: int = 0
    landing_page_views: int = 0
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
        external_adset_id: str,
        adset_name: str,
        external_ad_id: str,
        ad_name: str,
        metric_date: date,
        spend_original: Decimal | float | int | str,
        original_currency: str,
        fx_rates: dict[str, Decimal | float | str] | None = None,
        impressions: int = 0,
        reach: int = 0,
        clicks: int = 0,
        link_clicks: int = 0,
        landing_page_views: int = 0,
        conversions: Decimal | float | int | str = 0,
        conversion_value_usd: Decimal | float | int | str = 0,
        installs: int = 0,
        leads: int = 0,
    ) -> "DailyAdMetric":
        amount = Decimal(str(spend_original))
        spend_usd, rate = amount_to_usd(amount, original_currency, fx_rates)
        record = cls(
            brand_slug=brand_slug.strip().lower(),
            platform=platform.strip().lower(),
            external_account_id=external_account_id.strip(),
            external_campaign_id=external_campaign_id.strip(),
            campaign_name=campaign_name.strip(),
            external_adset_id=external_adset_id.strip(),
            adset_name=adset_name.strip(),
            external_ad_id=external_ad_id.strip(),
            ad_name=ad_name.strip(),
            metric_date=metric_date,
            spend_original=amount,
            original_currency=currency_code(original_currency),
            fx_to_usd=rate,
            spend_usd=spend_usd,
            impressions=int(impressions),
            reach=int(reach),
            clicks=int(clicks),
            link_clicks=int(link_clicks),
            landing_page_views=int(landing_page_views),
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
            "external_adset_id": self.external_adset_id,
            "adset_name": self.adset_name,
            "external_ad_id": self.external_ad_id,
            "ad_name": self.ad_name,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")
        numeric = {
            "spend_original": self.spend_original,
            "spend_usd": self.spend_usd,
            "impressions": self.impressions,
            "reach": self.reach,
            "clicks": self.clicks,
            "link_clicks": self.link_clicks,
            "landing_page_views": self.landing_page_views,
            "conversions": self.conversions,
            "conversion_value_usd": self.conversion_value_usd,
            "installs": self.installs,
            "leads": self.leads,
        }
        negative = [name for name, value in numeric.items() if value < 0]
        if negative:
            raise ValueError(f"Negative metrics are not allowed: {', '.join(negative)}")

    def to_ingest_row(self) -> dict[str, object]:
        return {
            "brand_slug": self.brand_slug,
            "platform": self.platform,
            "external_account_id": self.external_account_id,
            "external_campaign_id": self.external_campaign_id,
            "campaign_name": self.campaign_name,
            "external_adset_id": self.external_adset_id,
            "adset_name": self.adset_name,
            "external_ad_id": self.external_ad_id,
            "ad_name": self.ad_name,
            "metric_date": self.metric_date.isoformat(),
            "spend_original": str(self.spend_original),
            "original_currency": self.original_currency,
            "fx_to_usd": str(self.fx_to_usd),
            "spend_usd": str(self.spend_usd),
            "impressions": self.impressions,
            "reach": self.reach,
            "clicks": self.clicks,
            "link_clicks": self.link_clicks,
            "landing_page_views": self.landing_page_views,
            "conversions": str(self.conversions),
            "conversion_value_usd": str(self.conversion_value_usd),
            "installs": self.installs,
            "leads": self.leads,
        }


@dataclass(frozen=True, slots=True)
class AdEntity:
    """Current metadata for one ad, including ads with no delivery."""

    brand_slug: str
    platform: str
    external_account_id: str
    external_campaign_id: str
    campaign_name: str
    external_adset_id: str
    adset_name: str
    external_ad_id: str
    ad_name: str
    status: str
    effective_status: str
    creative_id: str | None = None
    created_time: datetime | None = None
    updated_time: datetime | None = None

    def validate(self) -> None:
        required = {
            "brand_slug": self.brand_slug,
            "platform": self.platform,
            "external_account_id": self.external_account_id,
            "external_campaign_id": self.external_campaign_id,
            "campaign_name": self.campaign_name,
            "external_adset_id": self.external_adset_id,
            "adset_name": self.adset_name,
            "external_ad_id": self.external_ad_id,
            "ad_name": self.ad_name,
            "status": self.status,
            "effective_status": self.effective_status,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

    def to_ingest_row(self) -> dict[str, object]:
        self.validate()
        return {
            "brand_slug": self.brand_slug.strip().lower(),
            "platform": self.platform.strip().lower(),
            "external_account_id": self.external_account_id.strip(),
            "external_campaign_id": self.external_campaign_id.strip(),
            "campaign_name": self.campaign_name.strip(),
            "external_adset_id": self.external_adset_id.strip(),
            "adset_name": self.adset_name.strip(),
            "external_ad_id": self.external_ad_id.strip(),
            "ad_name": self.ad_name.strip(),
            "status": self.status.strip(),
            "effective_status": self.effective_status.strip(),
            "creative_id": self.creative_id.strip() if self.creative_id else None,
            "created_time": self.created_time.isoformat() if self.created_time else None,
            "updated_time": self.updated_time.isoformat() if self.updated_time else None,
        }
