"""Server-side Supabase REST writer.

This module is for GitHub Actions or another trusted backend only. It requires
a Supabase secret key and must never be imported by browser code.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any, Protocol
from urllib.parse import urlparse

from .models import AdEntity, DailyAdMetric, DailyCampaignMetric
from .settings import AccountMapping


class HTTPSession(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> Any: ...


class SupabaseWriter:
    def __init__(
        self,
        url: str,
        secret_key: str,
        *,
        session: HTTPSession | None = None,
    ) -> None:
        parsed = urlparse(url.rstrip("/"))
        local = parsed.hostname in {"127.0.0.1", "localhost"}
        if parsed.scheme != "https" and not (local and parsed.scheme == "http"):
            raise ValueError("Supabase URL must use HTTPS")
        if not secret_key.strip():
            raise ValueError("Supabase secret key is required")
        self.base_url = f"{url.rstrip('/')}/rest/v1"
        if session is None:
            import requests

            session = requests.Session()
        self.session = session
        self.headers = {
            "apikey": secret_key,
            "Content-Type": "application/json",
        }
        self._account_ids: dict[tuple[str, str], str] = {}
        self._brand_ids: dict[str, str] = {}

    @classmethod
    def from_environment(cls) -> "SupabaseWriter":
        return cls(
            os.environ.get("SUPABASE_URL", ""),
            os.environ.get("SUPABASE_SECRET_KEY", ""),
        )

    def _request(self, method: str, table: str, **kwargs: Any) -> Any:
        headers = {**self.headers, **kwargs.pop("headers", {})}
        response = self.session.request(
            method,
            f"{self.base_url}/{table}",
            headers=headers,
            timeout=30,
            **kwargs,
        )
        response.raise_for_status()
        return response

    def _brand_id(self, slug: str) -> str:
        if slug in self._brand_ids:
            return self._brand_ids[slug]
        response = self._request(
            "GET", "brands", params={"slug": f"eq.{slug}", "select": "id"}
        )
        rows = response.json()
        if len(rows) != 1:
            raise ValueError(f"Brand {slug!r} is missing or not unique in Supabase")
        brand_id = str(rows[0]["id"])
        self._brand_ids[slug] = brand_id
        return brand_id

    def ensure_account(self, mapping: AccountMapping) -> str:
        identity = (mapping.platform, mapping.external_account_id)
        if identity in self._account_ids:
            return self._account_ids[identity]

        payload = {
            "brand_id": self._brand_id(mapping.brand_slug),
            "platform": mapping.platform,
            "external_account_id": mapping.external_account_id,
            "display_name": mapping.display_name,
            "account_currency": mapping.currency,
            "active": True,
        }
        response = self._request(
            "POST",
            "ad_accounts",
            params={"on_conflict": "platform,external_account_id"},
            json=[payload],
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        )
        rows = response.json()
        if len(rows) != 1 or not rows[0].get("id"):
            raise RuntimeError("Supabase did not return the upserted ad account")
        account_id = str(rows[0]["id"])
        self._account_ids[identity] = account_id
        return account_id

    def upsert_campaign_metrics(
        self,
        records: Iterable[DailyCampaignMetric],
        mappings: Iterable[AccountMapping],
        *,
        batch_size: int = 500,
    ) -> int:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        mapping_index = {
            (mapping.platform, mapping.external_account_id): mapping
            for mapping in mappings
        }
        rows: list[dict[str, object]] = []
        written = 0

        def flush() -> None:
            nonlocal written
            if not rows:
                return
            self._request(
                "POST",
                "campaign_metrics_daily",
                params={
                    "on_conflict": "ad_account_id,external_campaign_id,metric_date"
                },
                json=list(rows),
                headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            )
            written += len(rows)
            rows.clear()

        for record in records:
            identity = (record.platform, record.external_account_id)
            mapping = mapping_index.get(identity)
            if mapping is None:
                raise ValueError(
                    f"No brand mapping for {record.platform}/{record.external_account_id}"
                )
            if record.brand_slug != mapping.brand_slug:
                raise ValueError(
                    f"Record brand {record.brand_slug!r} conflicts with account mapping "
                    f"{mapping.brand_slug!r}"
                )
            payload = record.to_ingest_row()
            payload["brand_id"] = self._brand_id(record.brand_slug)
            payload["ad_account_id"] = self.ensure_account(mapping)
            payload.pop("brand_slug")
            payload.pop("external_account_id")
            rows.append(payload)
            if len(rows) >= batch_size:
                flush()
        flush()
        return written

    def upsert_ad_metrics(
        self,
        records: Iterable[DailyAdMetric],
        mappings: Iterable[AccountMapping],
        *,
        batch_size: int = 500,
    ) -> int:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        mapping_index = {
            (mapping.platform, mapping.external_account_id): mapping
            for mapping in mappings
        }
        rows: list[dict[str, object]] = []
        written = 0

        def flush() -> None:
            nonlocal written
            if not rows:
                return
            self._request(
                "POST",
                "ad_metrics_daily",
                params={"on_conflict": "ad_account_id,external_ad_id,metric_date"},
                json=list(rows),
                headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            )
            written += len(rows)
            rows.clear()

        for record in records:
            identity = (record.platform, record.external_account_id)
            mapping = mapping_index.get(identity)
            if mapping is None:
                raise ValueError(
                    f"No brand mapping for {record.platform}/{record.external_account_id}"
                )
            if record.brand_slug != mapping.brand_slug:
                raise ValueError(
                    f"Record brand {record.brand_slug!r} conflicts with account mapping "
                    f"{mapping.brand_slug!r}"
                )
            payload = record.to_ingest_row()
            payload["brand_id"] = self._brand_id(record.brand_slug)
            payload["ad_account_id"] = self.ensure_account(mapping)
            payload.pop("brand_slug")
            payload.pop("external_account_id")
            rows.append(payload)
            if len(rows) >= batch_size:
                flush()
        flush()
        return written

    def upsert_ad_entities(
        self,
        records: Iterable[AdEntity],
        mappings: Iterable[AccountMapping],
        *,
        batch_size: int = 500,
    ) -> int:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        mapping_index = {
            (mapping.platform, mapping.external_account_id): mapping
            for mapping in mappings
        }
        rows: list[dict[str, object]] = []
        written = 0

        def flush() -> None:
            nonlocal written
            if not rows:
                return
            self._request(
                "POST",
                "ad_entities",
                params={"on_conflict": "ad_account_id,external_ad_id"},
                json=list(rows),
                headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            )
            written += len(rows)
            rows.clear()

        for record in records:
            identity = (record.platform, record.external_account_id)
            mapping = mapping_index.get(identity)
            if mapping is None:
                raise ValueError(
                    f"No brand mapping for {record.platform}/{record.external_account_id}"
                )
            if record.brand_slug != mapping.brand_slug:
                raise ValueError(
                    f"Record brand {record.brand_slug!r} conflicts with account mapping "
                    f"{mapping.brand_slug!r}"
                )
            payload = record.to_ingest_row()
            payload["brand_id"] = self._brand_id(record.brand_slug)
            payload["ad_account_id"] = self.ensure_account(mapping)
            payload.pop("brand_slug")
            payload.pop("external_account_id")
            rows.append(payload)
            if len(rows) >= batch_size:
                flush()
        flush()
        return written
