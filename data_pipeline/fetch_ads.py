#!/usr/bin/env python3
"""
Samla Digital — Real-time ad-platform fetcher.

Pulls account-level performance from Google Ads, Meta Ads, LinkedIn Ads, and
TikTok Ads, and writes a consolidated JSON file the dashboard consumes.

Run once: python3 fetch_ads.py
Run on schedule: see scheduled-task wiring in the README.

Each platform is wrapped in try/except so one broken credential doesn't kill
the whole run — the missing platform is simply marked {"status": "error", ...}
in the output JSON, and the dashboard renders it as "needs reconnect".
"""
from __future__ import annotations

import json
import os
import sys
import time
import logging
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

try:
    import requests  # noqa: F401
except ImportError:
    print("Install deps first:  pip3 install --break-system-packages requests python-dotenv")
    sys.exit(1)

import requests
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

OUTPUT_PATH = Path(os.getenv("OUTPUT_PATH", HERE / "live_data.json"))
LOG_PATH = Path(os.getenv("LOG_PATH", HERE / "fetch.log"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("samla.fetch")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _ok(platform: str, **fields: Any) -> dict:
    return {"platform": platform, "status": "ok", "fetched_at": datetime.now(timezone.utc).isoformat(), **fields}


def _err(platform: str, error: str) -> dict:
    return {"platform": platform, "status": "error", "error": error, "fetched_at": datetime.now(timezone.utc).isoformat()}


def _need(*keys: str) -> bool:
    return all(os.getenv(k) for k in keys)


# ──────────────────────────────────────────────────────────────────────────────
# Google Ads — uses google-ads REST endpoint via OAuth refresh token
# Docs: https://developers.google.com/google-ads/api/rest/auth
# ──────────────────────────────────────────────────────────────────────────────
def fetch_google_ads() -> dict:
    if not _need("GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID",
                 "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN",
                 "GOOGLE_ADS_CUSTOMER_ID"):
        return _err("google_ads", "missing credentials in .env")
    try:
        # 1) Exchange refresh token for access token
        token_resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
                "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
                "grant_type": "refresh_token",
            },
            timeout=20,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        # 2) Run a GAQL search query for account-level lifetime metrics
        cust = os.environ["GOOGLE_ADS_CUSTOMER_ID"].replace("-", "")
        login_cust = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").replace("-", "")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
            "Content-Type": "application/json",
        }
        if login_cust:
            headers["login-customer-id"] = login_cust

        # Lifetime totals — segments.date is unbounded so this returns since-account-creation
        query = """
            SELECT metrics.cost_micros, metrics.impressions, metrics.clicks,
                   metrics.conversions, metrics.conversions_value
            FROM customer
        """
        r = requests.post(
            f"https://googleads.googleapis.com/v17/customers/{cust}/googleAds:search",
            headers=headers,
            json={"query": query},
            timeout=30,
        )
        r.raise_for_status()
        rows = r.json().get("results", [])
        spend = sum(int(row["metrics"].get("costMicros", 0)) for row in rows) / 1e6
        impressions = sum(int(row["metrics"].get("impressions", 0)) for row in rows)
        clicks = sum(int(row["metrics"].get("clicks", 0)) for row in rows)
        conversions = sum(float(row["metrics"].get("conversions", 0)) for row in rows)
        conv_value = sum(float(row["metrics"].get("conversionsValue", 0)) for row in rows)

        return _ok(
            "google_ads",
            spend=round(spend, 2),
            impressions=impressions,
            clicks=clicks,
            conversions=round(conversions, 2),
            conversion_value=round(conv_value, 2),
            ctr=round(clicks / impressions * 100, 3) if impressions else 0,
            cpc=round(spend / clicks, 3) if clicks else 0,
            roas=round(conv_value / spend, 2) if spend else 0,
        )
    except Exception as e:  # noqa: BLE001
        log.error("google_ads failed: %s\n%s", e, traceback.format_exc())
        return _err("google_ads", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Meta Ads — Graph API insights endpoint
# Docs: https://developers.facebook.com/docs/marketing-api/insights
# ──────────────────────────────────────────────────────────────────────────────
def fetch_meta_ads() -> dict:
    if not _need("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID"):
        return _err("meta_ads", "missing credentials in .env")
    try:
        token = os.environ["META_ACCESS_TOKEN"]
        acct = os.environ["META_AD_ACCOUNT_ID"]
        if not acct.startswith("act_"):
            acct = f"act_{acct}"

        url = f"https://graph.facebook.com/v21.0/{acct}/insights"
        params = {
            "fields": "spend,impressions,clicks,cpc,ctr,actions,action_values",
            "date_preset": "maximum",  # account-lifetime
            "access_token": token,
            "level": "account",
        }
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return _ok("meta_ads", spend=0, impressions=0, clicks=0, conversions=0)

        row = data[0]
        actions = {a["action_type"]: float(a["value"]) for a in row.get("actions", [])}
        action_values = {a["action_type"]: float(a["value"]) for a in row.get("action_values", [])}
        leads = actions.get("lead", 0)
        purchases = actions.get("purchase", 0)
        purchase_value = action_values.get("purchase", 0)

        return _ok(
            "meta_ads",
            spend=float(row.get("spend", 0)),
            impressions=int(row.get("impressions", 0)),
            clicks=int(row.get("clicks", 0)),
            cpc=float(row.get("cpc", 0)),
            ctr=float(row.get("ctr", 0)),
            leads=leads,
            purchases=purchases,
            purchase_value=purchase_value,
            roas=round(purchase_value / float(row.get("spend", 0)), 2)
                 if float(row.get("spend", 0)) else 0,
        )
    except Exception as e:  # noqa: BLE001
        log.error("meta_ads failed: %s\n%s", e, traceback.format_exc())
        return _err("meta_ads", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# LinkedIn Ads — Marketing API
# Docs: https://learn.microsoft.com/en-us/linkedin/marketing/integrations/ads-reporting/ads-reporting
# ──────────────────────────────────────────────────────────────────────────────
def fetch_linkedin_ads() -> dict:
    if not _need("LINKEDIN_ACCESS_TOKEN", "LINKEDIN_AD_ACCOUNT_ID"):
        return _err("linkedin_ads", "missing credentials in .env")
    try:
        token = os.environ["LINKEDIN_ACCESS_TOKEN"]
        acct = os.environ["LINKEDIN_AD_ACCOUNT_ID"]
        # LinkedIn requires a date range; use 2010-01-01 → today as account-lifetime proxy
        today = datetime.now(timezone.utc).date()
        params = {
            "q": "analytics",
            "pivot": "ACCOUNT",
            "timeGranularity": "ALL",
            "dateRange.start.year": 2010,
            "dateRange.start.month": 1,
            "dateRange.start.day": 1,
            "dateRange.end.year": today.year,
            "dateRange.end.month": today.month,
            "dateRange.end.day": today.day,
            "accounts[0]": f"urn:li:sponsoredAccount:{acct}",
            "fields": "costInLocalCurrency,impressions,clicks,externalWebsiteConversions,oneClickLeads",
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "LinkedIn-Version": "202410",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        r = requests.get(
            "https://api.linkedin.com/rest/adAnalytics",
            params=params, headers=headers, timeout=30,
        )
        r.raise_for_status()
        elements = r.json().get("elements", [])
        if not elements:
            return _ok("linkedin_ads", spend=0, impressions=0, clicks=0, conversions=0, leads=0)

        agg = elements[0]
        spend = float(agg.get("costInLocalCurrency", 0))
        impressions = int(agg.get("impressions", 0))
        clicks = int(agg.get("clicks", 0))
        conversions = int(agg.get("externalWebsiteConversions", 0))
        leads = int(agg.get("oneClickLeads", 0))
        return _ok(
            "linkedin_ads",
            spend=round(spend, 2),
            impressions=impressions,
            clicks=clicks,
            conversions=conversions,
            leads=leads,
            ctr=round(clicks / impressions * 100, 3) if impressions else 0,
            cpc=round(spend / clicks, 3) if clicks else 0,
        )
    except Exception as e:  # noqa: BLE001
        log.error("linkedin_ads failed: %s\n%s", e, traceback.format_exc())
        return _err("linkedin_ads", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# TikTok Ads — Business API integrated report
# Docs: https://business-api.tiktok.com/portal/docs?id=1740302848100353
# ──────────────────────────────────────────────────────────────────────────────
def fetch_tiktok_ads() -> dict:
    if not _need("TIKTOK_ACCESS_TOKEN", "TIKTOK_ADVERTISER_ID"):
        return _err("tiktok_ads", "missing credentials in .env")
    try:
        token = os.environ["TIKTOK_ACCESS_TOKEN"]
        advertiser_id = os.environ["TIKTOK_ADVERTISER_ID"]
        # TikTok caps queryable history to ~3 years; use a generous window
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=365 * 3)

        body = {
            "advertiser_id": advertiser_id,
            "report_type": "BASIC",
            "data_level": "AUCTION_ADVERTISER",
            "dimensions": ["advertiser_id"],
            "metrics": ["spend", "impressions", "clicks", "ctr", "cpc",
                        "conversion", "conversion_value", "result"],
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "page_size": 1,
        }
        r = requests.get(
            "https://business-api.tiktok.com/open_api/v1.3/report/integrated/get/",
            params={k: json.dumps(v) if isinstance(v, list) else v for k, v in body.items()},
            headers={"Access-Token": token},
            timeout=30,
        )
        r.raise_for_status()
        payload = r.json()
        if payload.get("code") != 0:
            return _err("tiktok_ads", payload.get("message", "unknown error"))
        rows = payload.get("data", {}).get("list", [])
        if not rows:
            return _ok("tiktok_ads", spend=0, impressions=0, clicks=0)
        m = rows[0].get("metrics", {})
        spend = float(m.get("spend", 0))
        impressions = int(m.get("impressions", 0))
        clicks = int(m.get("clicks", 0))
        conversion = float(m.get("conversion", 0))
        conv_value = float(m.get("conversion_value", 0))
        leads = int(m.get("result", 0))
        return _ok(
            "tiktok_ads",
            spend=round(spend, 2),
            impressions=impressions,
            clicks=clicks,
            ctr=float(m.get("ctr", 0)),
            cpc=float(m.get("cpc", 0)),
            conversions=conversion,
            conversion_value=conv_value,
            leads=leads,
            roas=round(conv_value / spend, 2) if spend else 0,
        )
    except Exception as e:  # noqa: BLE001
        log.error("tiktok_ads failed: %s\n%s", e, traceback.format_exc())
        return _err("tiktok_ads", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Snapchat Ads — Marketing API
# Docs: https://marketingapi.snapchat.com/docs/
# ──────────────────────────────────────────────────────────────────────────────
def fetch_snapchat_ads() -> dict:
    if not _need("SNAPCHAT_CLIENT_ID", "SNAPCHAT_CLIENT_SECRET", "SNAPCHAT_REFRESH_TOKEN", "SNAPCHAT_AD_ACCOUNT_ID"):
        return _err("snapchat_ads", "missing credentials in .env")
    try:
        # 1) Exchange refresh token for access token
        token_resp = requests.post(
            "https://accounts.snapchat.com/login/oauth2/access_token",
            data={
                "client_id": os.environ["SNAPCHAT_CLIENT_ID"],
                "client_secret": os.environ["SNAPCHAT_CLIENT_SECRET"],
                "refresh_token": os.environ["SNAPCHAT_REFRESH_TOKEN"],
                "grant_type": "refresh_token",
            },
            timeout=20,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        acct = os.environ["SNAPCHAT_AD_ACCOUNT_ID"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Account-lifetime stats
        params = {
            "granularity": "LIFETIME",
            "fields": "spend,impressions,swipes"
        }
        r = requests.get(
            f"https://adsapi.snapchat.com/v1/adaccounts/{acct}/stats",
            headers=headers,
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        stats = r.json().get("timeseries_stats", [])
        if not stats or not stats[0].get("timeseries_stat", {}).get("stats"):
            return _ok("snapchat_ads", spend=0, impressions=0, clicks=0)
            
        data = stats[0]["timeseries_stat"]["stats"]
        spend = float(data.get("spend", 0)) / 1000000.0 # Snap spend is usually in micro-currency
        impressions = int(data.get("impressions", 0))
        clicks = int(data.get("swipes", 0))
        
        return _ok(
            "snapchat_ads",
            spend=round(spend, 2),
            impressions=impressions,
            clicks=clicks,
            ctr=round(clicks / impressions * 100, 3) if impressions else 0,
            cpc=round(spend / clicks, 3) if clicks else 0,
        )
    except Exception as e:  # noqa: BLE001
        log.error("snapchat_ads failed: %s\n%s", e, traceback.format_exc())
        return _err("snapchat_ads", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Steam — public store API + optional Web API key
# Docs: https://partner.steamgames.com/doc/webapi
# ──────────────────────────────────────────────────────────────────────────────
def fetch_steam() -> dict:
    app_id = os.getenv("STEAM_APP_ID", "").strip()
    if not app_id:
        return _err("steam", "STEAM_APP_ID not set in .env")
    out = {"app_id": app_id}
    try:
        # 1) Public storefront details — name, release date, price (no key needed)
        r = requests.get(
            "https://store.steampowered.com/api/appdetails",
            params={"appids": app_id, "filters": "basic,release_date,price_overview"},
            timeout=20,
        )
        r.raise_for_status()
        body = r.json().get(str(app_id), {})
        if body.get("success") and body.get("data"):
            d = body["data"]
            out.update({
                "name": d.get("name"),
                "release_date": (d.get("release_date") or {}).get("date"),
                "coming_soon": (d.get("release_date") or {}).get("coming_soon"),
                "price": ((d.get("price_overview") or {}).get("final_formatted")),
            })
        else:
            out["details_status"] = "not_found_or_unreleased"

        # 2) Current player count — public, no key needed
        try:
            pc = requests.get(
                "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/",
                params={"appid": app_id},
                timeout=15,
            )
            pc.raise_for_status()
            out["current_players"] = pc.json().get("response", {}).get("player_count")
        except Exception as e:  # noqa: BLE001
            out["current_players_error"] = str(e)

        # 3) Review summary — public, no key needed
        try:
            rv = requests.get(
                f"https://store.steampowered.com/appreviews/{app_id}",
                params={"json": 1, "language": "all", "purchase_type": "all", "num_per_page": 0},
                timeout=15,
            )
            rv.raise_for_status()
            qs = rv.json().get("query_summary", {})
            out.update({
                "total_reviews": qs.get("total_reviews"),
                "review_score_desc": qs.get("review_score_desc"),
                "total_positive": qs.get("total_positive"),
                "total_negative": qs.get("total_negative"),
            })
        except Exception as e:  # noqa: BLE001
            out["reviews_error"] = str(e)

        # 4) Wishlist count — requires Steamworks PARTNER key (not the public Web API key).
        # The partner endpoint shape varies by partner program; left as a stub the user can
        # extend with their specific partner credentials.
        if os.getenv("STEAM_PARTNER_API_KEY"):
            out["wishlist_note"] = "STEAM_PARTNER_API_KEY set — extend fetch_steam() with the partner endpoint your account exposes"

        return _ok("steam", **out)
    except Exception as e:  # noqa: BLE001
        log.error("steam failed: %s\n%s", e, traceback.format_exc())
        return _err("steam", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────────────────
def main() -> int:
    started = time.time()
    log.info("Fetcher run started.")

    platforms = {
        "google_ads": fetch_google_ads(),
        "meta_ads": fetch_meta_ads(),
        "linkedin_ads": fetch_linkedin_ads(),
        "tiktok_ads": fetch_tiktok_ads(),
        "snapchat_ads": fetch_snapchat_ads(),
        "steam": fetch_steam(),
    }

    # Cross-platform totals (only count platforms that succeeded)
    ok = [p for p in platforms.values() if p["status"] == "ok"]
    totals = {
        "spend": round(sum(p.get("spend", 0) for p in ok), 2),
        "impressions": sum(p.get("impressions", 0) for p in ok),
        "clicks": sum(p.get("clicks", 0) for p in ok),
        "conversions": round(sum(p.get("conversions", 0) for p in ok), 2),
        "leads": sum(p.get("leads", 0) for p in ok),
        "platforms_ok": [p["platform"] for p in ok],
        "platforms_error": [p["platform"] for p in platforms.values() if p["status"] == "error"],
    }

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.time() - started, 2),
        "totals": totals,
        "platforms": platforms,
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    # Also emit a JS wrapper so HTML dashboards opened via file:// can pick it
    # up directly via <script src="data_pipeline/live_data.js"></script>.
    # `window.SAMLA_LIVE` mirrors the JSON exactly.
    js_path = Path(os.getenv("JS_OUTPUT_PATH", HERE / "live_data.js"))
    js_path.write_text(
        "// Auto-generated by fetch_ads.py — do not edit by hand.\n"
        "window.SAMLA_LIVE = " + json.dumps(output, indent=2) + ";\n"
    )

    log.info("Wrote %s and %s — %d platforms ok, %d errored.",
             OUTPUT_PATH, js_path,
             len(totals["platforms_ok"]), len(totals["platforms_error"]))
    return 0 if totals["platforms_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
