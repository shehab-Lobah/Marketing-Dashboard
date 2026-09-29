# Lobah Marketing Dashboard — Data Pipeline

> Foundation status: the historical Supabase model and canonical daily record
> are ready. `fetch_ads.py` is the legacy account-total prototype and must not
> be used as the source for weekly, quarterly or YTD reporting. It will be
> replaced platform by platform in Phases 2–3.

The production pipeline stores the complete ad catalog plus daily campaign
and ad observations for SAMLA and Jackaroo Strike, preserving source currency
and normalized USD spend. See
[`../ARCHITECTURE.md`](../ARCHITECTURE.md) and the migration in
`../supabase/migrations/` for the reporting contract.

## Setup (one-time)

```bash
cd "/Users/shehabeldin/Library/CloudStorage/Dropbox/Samla Digital/data_pipeline"
pip3 install --break-system-packages requests python-dotenv
cp .env.example .env
# edit .env and fill in real credentials
```

## Where to get each credential

**Google Ads**
1. Apply for a developer token: https://ads.google.com/aw/apicenter
2. Create OAuth credentials in Google Cloud Console (Web app type).
3. Mint a refresh token: easiest path is the OAuth Playground
   (https://developers.google.com/oauthplayground) with scope
   `https://www.googleapis.com/auth/adwords` and "Use your own credentials" checked.
4. Find your customer ID at the top of the Google Ads UI (e.g. `123-456-7890`).

**Meta Ads**
1. Open Business Manager → Business Settings → System Users → Add → Admin.
2. Generate Token, give it `ads_read` and `business_management` scopes.
3. Ad account id: in Ads Manager URL, `act_<digits>` is the value.

**LinkedIn Ads**
1. Create an app at https://www.linkedin.com/developers/apps.
2. Request products: "Advertising API" and "Marketing Developer Platform".
3. OAuth a user with scopes `r_ads`, `r_ads_reporting`.
4. Tokens last 60 days — re-mint via your app or `scripts/oauth_linkedin.py`.

**TikTok Ads**
1. Create a TikTok for Business app: https://business-api.tiktok.com/portal/.
2. OAuth in, exchange code for long-lived access token.
3. Advertiser ID is in the Ads Manager URL.

## Running the production Meta sync

```bash
python -m data_pipeline.sync_paid --platform meta --days 7
```

To backfill every day from the first known Meta activity:

```bash
python -m data_pipeline.sync_paid \
  --platform meta \
  --start 2025-12-14 \
  --end 2026-09-13
```

The sync upserts the complete ad catalog, daily campaign metrics and daily
ad metrics into Supabase. Re-running an overlapping range is safe.

## Schedule it

GitHub Actions refreshes the latest seven days hourly and reconciles the latest
30 days nightly. The manual workflow accepts either a rolling `days` window or
an explicit historical `start` and `end` range.

## Output shape

```json
{
  "generated_at": "2026-05-04T...",
  "totals": { "spend": 12345.67, "impressions": 9876543, ... },
  "platforms": {
    "google_ads":   { "status": "ok", "spend": ..., "impressions": ..., ... },
    "meta_ads":     { "status": "ok", ... },
    "linkedin_ads": { "status": "error", "error": "missing credentials in .env" },
    "tiktok_ads":   { "status": "ok", ... }
  }
}
```

The dashboard renders error platforms as "needs reconnect" badges so you can
see at a glance which credential is stale.
