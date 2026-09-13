"""Meta Marketing API daily campaign collector."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..currency import amount_to_usd
from ..models import DailyCampaignMetric
from ..settings import AccountMapping


class HTTPClient(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


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
    if mapping.platform != "meta_ads":
        raise ValueError("Meta collector requires a meta_ads account mapping")
    if not access_token.strip():
        raise ValueError("Meta access token is required")
    if not re.fullmatch(r"v\d+\.\d+", api_version.strip()):
        raise ValueError("Meta API version must use the form vNN.N")
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
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
        "level": "campaign",
        "fields": (
            "campaign_id,campaign_name,spend,impressions,clicks,actions,action_values"
        ),
        "time_range": json.dumps(
            {"since": start_date.isoformat(), "until": end_date.isoformat()}
        ),
        "time_increment": 1,
        "limit": 500,
    }
    records: list[DailyCampaignMetric] = []
    headers = {"Authorization": f"Bearer {access_token}"}

    while url:
        response = client.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        for row in payload.get("data", []):
            actions = _action_map(row.get("actions"))
            action_values = _action_map(row.get("action_values"))
            purchases = _first_action(
                actions, ("purchase", "offsite_conversion.fb_pixel_purchase")
            )
            leads = _first_action(actions, ("lead", "onsite_conversion.lead_grouped"))
            installs = _first_action(
                actions, ("mobile_app_install", "omni_app_install")
            )
            purchase_value = _first_action(
                action_values, ("purchase", "offsite_conversion.fb_pixel_purchase")
            )
            purchase_value_usd, _ = amount_to_usd(
                purchase_value, mapping.currency, fx_rates
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
                    clicks=row.get("clicks", 0),
                    conversions=purchases,
                    conversion_value_usd=purchase_value_usd,
                    installs=int(installs),
                    leads=int(leads),
                )
            )
        next_url = payload.get("paging", {}).get("next")
        url = _without_access_token(str(next_url)) if next_url else None
        params = None
    return records
