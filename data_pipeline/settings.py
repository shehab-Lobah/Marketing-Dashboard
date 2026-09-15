"""Validated non-secret configuration for account-to-brand ownership."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .currency import currency_code


SUPPORTED_PLATFORMS = {
    "meta_ads",
    "tiktok_ads",
    "google_ads",
    "snapchat_ads",
    "linkedin_ads",
}


@dataclass(frozen=True, slots=True)
class AccountMapping:
    brand_slug: str
    platform: str
    external_account_id: str
    display_name: str
    currency: str


def load_account_mappings(path: str | Path) -> list[AccountMapping]:
    config_path = Path(path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    accounts = raw.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("brand mapping must contain a non-empty accounts list")

    result: list[AccountMapping] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(accounts):
        if not isinstance(item, dict):
            raise ValueError(f"accounts[{index}] must be an object")
        required = (
            "brand_slug",
            "platform",
            "external_account_id",
            "display_name",
            "currency",
        )
        missing = [key for key in required if not str(item.get(key, "")).strip()]
        if missing:
            raise ValueError(f"accounts[{index}] missing: {', '.join(missing)}")

        platform = str(item["platform"]).strip().lower()
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"accounts[{index}] has unsupported platform {platform!r}")
        external_id = str(item["external_account_id"]).strip()
        identity = (platform, external_id)
        if identity in seen:
            raise ValueError(f"duplicate account mapping for {platform}/{external_id}")
        seen.add(identity)

        result.append(
            AccountMapping(
                brand_slug=str(item["brand_slug"]).strip().lower(),
                platform=platform,
                external_account_id=external_id,
                display_name=str(item["display_name"]).strip(),
                currency=currency_code(str(item["currency"])),
            )
        )
    return result


def accounts_for_platform(
    mappings: list[AccountMapping], platform: str
) -> list[AccountMapping]:
    wanted = platform.strip().lower()
    return [account for account in mappings if account.platform == wanted]

