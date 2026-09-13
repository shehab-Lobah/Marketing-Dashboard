"""Meta Marketing API daily campaign collector."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..currency import amount_to_usd
from ..models import AdEntity, DailyAdMetric, DailyCampaignMetric
from ..settings import AccountMapping


class HTTPClient(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


def discover_meta_ad_accounts(
    *,
    access_token: str,
    api_version: str,
    client: HTTPClient | None = None,
) -> list[dict[str, str]]:
    """List ad accounts available to the token without exposing the token."""
    if not access_token.strip():
        raise ValueError("Meta access token is required")
    if not re.fullmatch(r"v\d+\.\d+", api_version.strip()):
        raise ValueError("Meta API version must use the form vNN.N")
    if client is None:
        import requests

        client = requests.Session()

    url: str | None = (
        f"https://graph.facebook.com/{api_version.strip()}/me/adaccounts"
    )
    params: dict[str, object] | None = {
        "fields": "id,name,currency,account_status",
        "limit": 500,
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    accounts: list[dict[str, str]] = []

    while url:
        response = client.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        for row in payload.get("data", []):
            account_id = str(row.get("id", "")).strip()
            if not account_id:
                continue
            accounts.append(
                {
                    "external_account_id": account_id,
                    "display_name": str(row.get("name") or account_id),
                    "currency": str(row.get("currency") or "USD").upper(),
                    "account_status": str(row.get("account_status") or ""),
                }
            )
        next_url = payload.get("paging", {}).get("next")
        url = _without_access_token(str(next_url)) if next_url else None
        params = None

    return accounts


def _action_map(values: list[dict[str, str]] | None) -> dict[str, Decimal]:
    return {
        str(item.get("action_type", "")): Decimal(str(item.get("value", "0")))
        for item in (values or [])
        if item.get("action_type")
    }


def _first_action(actions: Mapping[str, Decimal], names: tuple[str, ...]) -> Decimal:
    for name in names:
        if name in actions:
            return actions[name]
    return Decimal("0")


def _without_access_token(url: str) -> str:
    """Remove token parameters Meta may include in pagination links."""
    parts = urlsplit(url)
    query = urlencode(
        [
            (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() != "access_token"
        ]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _validate_request(
    mapping: AccountMapping,
    access_token: str,
    api_version: str,
    start_date: date,
    end_date: date,
) -> None:
    if mapping.platform != "meta_ads":
        raise ValueError("Meta collector requires a meta_ads account mapping")
    if not access_token.strip():
        raise ValueError("Meta access token is required")
    if not re.fullmatch(r"v\d+\.\d+", api_version.strip()):
        raise ValueError("Meta API version must use the form vNN.N")
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")


def _fetch_daily_insights(
    mapping: AccountMapping,
    *,
    access_token: str,
    api_version: str,
    start_date: date,
    end_date: date,
    level: str,
    fields: str,
    client: HTTPClient | None,
) -> list[dict[str, Any]]:
    _validate_request(mapping, access_token, api_version, start_date, end_date)
    if client is None:
        import requests

        client = requests.Session()

    account_id = mapping.external_account_id
    if not account_id.startswith("act_"):
        account_id = f"act_{account_id}"
    url: str | None = (
        f"https://graph.facebook.com/{api_version.strip()}/{account_id}/insights"
    )
    params: dict[str, object] | None = {
        "level": level,
        "fields": fields,
        "time_range": json.dumps(
            {"since": start_date.isoformat(), "until": end_date.isoformat()}
        ),
        "time_increment": 1,
        "limit": 500,
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    rows: list[dict[str, Any]] = []

    while url:
        response = client.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        rows.extend(payload.get("data", []))
        next_url = payload.get("paging", {}).get("next")
        url = _without_access_token(str(next_url)) if next_url else None
        params = None
    return rows


def _conversion_metrics(
    row: Mapping[str, Any],
    mapping: AccountMapping,
    fx_rates: Mapping[str, Decimal | float | str] | None,
) -> tuple[Decimal, Decimal, int, int, int]:
    actions = _action_map(row.get("actions"))
    action_values = _action_map(row.get("action_values"))
    purchases = _first_action(
        actions, ("purchase", "offsite_conversion.fb_pixel_purchase")
    )
    leads = _first_action(actions, ("lead", "onsite_conversion.lead_grouped"))
    installs = _first_action(actions, ("mobile_app_install", "omni_app_install"))
    landing_page_views = _first_action(actions, ("landing_page_view",))
    purchase_value = _first_action(
        action_values, ("purchase", "offsite_conversion.fb_pixel_purchase")
    )
    purchase_value_usd, _ = amount_to_usd(
        purchase_value, mapping.currency, fx_rates
    )
    return purchases, purchase_value_usd, int(installs), int(leads), int(landing_page_views)


def collect_meta_daily(
    mapping: AccountMapping,
    *,
    access_token: str,
    api_version: str,
    start_date: date,
    end_date: date,
    fx_rates: Mapping[str, Decimal | float | str] | None = None,
    client: HTTPClient | None = None,
) -> list[DailyCampaignMetric]:
    """Fetch daily campaign rows for one mapped Meta ad account."""
    rows = _fetch_daily_insights(
        mapping,
        access_token=access_token,
        api_version=api_version,
        start_date=start_date,
        end_date=end_date,
        level="campaign",
        fields=(
            "campaign_id,campaign_name,spend,impressions,reach,clicks,"
            "inline_link_clicks,actions,action_values"
        ),
        client=client,
    )
    records: list[DailyCampaignMetric] = []
    for row in rows:
        purchases, purchase_value_usd, installs, leads, landing_page_views = (
            _conversion_metrics(row, mapping, fx_rates)
        )
        records.append(
            DailyCampaignMetric.build(
                brand_slug=mapping.brand_slug,
                platform=mapping.platform,
                external_account_id=mapping.external_account_id,
                external_campaign_id=str(row["campaign_id"]),
                campaign_name=str(row.get("campaign_name") or row["campaign_id"]),
                metric_date=date.fromisoformat(row["date_start"]),
                spend_original=row.get("spend", 0),
                original_currency=mapping.currency,
                fx_rates=dict(fx_rates or {}),
                impressions=row.get("impressions", 0),
                reach=row.get("reach", 0),
                clicks=row.get("clicks", 0),
                link_clicks=row.get("inline_link_clicks", 0),
                landing_page_views=landing_page_views,
                conversions=purchases,
                conversion_value_usd=purchase_value_usd,
                installs=installs,
                leads=leads,
            )
        )
    return records


def collect_meta_ad_daily(
    mapping: AccountMapping,
    *,
    access_token: str,
    api_version: str,
    start_date: date,
    end_date: date,
    fx_rates: Mapping[str, Decimal | float | str] | None = None,
    client: HTTPClient | None = None,
) -> list[DailyAdMetric]:
    """Fetch every ad's daily metrics for one mapped Meta ad account."""
    rows = _fetch_daily_insights(
        mapping,
        access_token=access_token,
        api_version=api_version,
        start_date=start_date,
        end_date=end_date,
        level="ad",
        fields=(
            "campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,"
            "spend,impressions,reach,clicks,inline_link_clicks,actions,action_values"
        ),
        client=client,
    )
    records: list[DailyAdMetric] = []
    for row in rows:
        purchases, purchase_value_usd, installs, leads, landing_page_views = (
            _conversion_metrics(row, mapping, fx_rates)
        )
        records.append(
            DailyAdMetric.build(
                brand_slug=mapping.brand_slug,
                platform=mapping.platform,
                external_account_id=mapping.external_account_id,
                external_campaign_id=str(row["campaign_id"]),
                campaign_name=str(row.get("campaign_name") or row["campaign_id"]),
                external_adset_id=str(row["adset_id"]),
                adset_name=str(row.get("adset_name") or row["adset_id"]),
                external_ad_id=str(row["ad_id"]),
                ad_name=str(row.get("ad_name") or row["ad_id"]),
                metric_date=date.fromisoformat(row["date_start"]),
                spend_original=row.get("spend", 0),
                original_currency=mapping.currency,
                fx_rates=dict(fx_rates or {}),
                impressions=row.get("impressions", 0),
                reach=row.get("reach", 0),
                clicks=row.get("clicks", 0),
                link_clicks=row.get("inline_link_clicks", 0),
                landing_page_views=landing_page_views,
                conversions=purchases,
                conversion_value_usd=purchase_value_usd,
                installs=installs,
                leads=leads,
            )
        )
    return records


def collect_meta_ads_catalog(
    mapping: AccountMapping,
    *,
    access_token: str,
    api_version: str,
    client: HTTPClient | None = None,
) -> list[AdEntity]:
    """Fetch the complete ad catalog, including ads with no delivery."""
    if mapping.platform != "meta_ads":
        raise ValueError("Meta collector requires a meta_ads account mapping")
    if not access_token.strip():
        raise ValueError("Meta access token is required")
    if not re.fullmatch(r"v\d+\.\d+", api_version.strip()):
        raise ValueError("Meta API version must use the form vNN.N")
    if client is None:
        import requests

        client = requests.Session()

    account_id = mapping.external_account_id
    if not account_id.startswith("act_"):
        account_id = f"act_{account_id}"
    url: str | None = f"https://graph.facebook.com/{api_version.strip()}/{account_id}/ads"
    params: dict[str, object] | None = {
        "fields": (
            "id,name,status,effective_status,created_time,updated_time,"
            "campaign{id,name},adset{id,name},creative{id}"
        ),
        "limit": 500,
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    records: list[AdEntity] = []

    while url:
        response = client.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        for row in payload.get("data", []):
            campaign = row.get("campaign") or {}
            adset = row.get("adset") or {}
            creative = row.get("creative") or {}
            record = AdEntity(
                brand_slug=mapping.brand_slug,
                platform=mapping.platform,
                external_account_id=mapping.external_account_id,
                external_campaign_id=str(campaign.get("id") or ""),
                campaign_name=str(campaign.get("name") or campaign.get("id") or ""),
                external_adset_id=str(adset.get("id") or ""),
                adset_name=str(adset.get("name") or adset.get("id") or ""),
                external_ad_id=str(row.get("id") or ""),
                ad_name=str(row.get("name") or row.get("id") or ""),
                status=str(row.get("status") or "UNKNOWN"),
                effective_status=str(row.get("effective_status") or "UNKNOWN"),
                creative_id=str(creative.get("id")) if creative.get("id") else None,
                created_time=(
                    datetime.fromisoformat(str(row["created_time"]))
                    if row.get("created_time")
                    else None
                ),
                updated_time=(
                    datetime.fromisoformat(str(row["updated_time"]))
                    if row.get("updated_time")
                    else None
                ),
            )
            record.validate()
            records.append(record)
        next_url = payload.get("paging", {}).get("next")
        url = _without_access_token(str(next_url)) if next_url else None
        params = None
    return records
