# Marketing Dashboard architecture

## Reporting contract

- Store one row per brand, platform, ad account, campaign and calendar day.
- Treat API values as source observations; do not substitute missing values with zero.
- Keep SAMLA and Jackaroo Strike separate at ingestion time.
- Preserve original spend, original currency, the dated FX rate and normalized USD spend.
- Compute CTR, CPC, CPI and ROAS from summed numerators and denominators.
- Derive weekly, quarterly and year-to-date results from daily records.
- Use `Asia/Riyadh` for report boundaries unless a source requires a documented exception.

## Runtime

1. GitHub Actions requests a bounded daily window from each platform.
2. Collectors normalize the responses to `DailyCampaignMetric` records.
3. A server-only secret-key connection upserts those rows into Supabase.
4. Supabase views calculate weekly, quarterly and YTD aggregates.
5. The authenticated dashboard reads reporting views using the public anon key and user session.
6. PDF and PowerPoint exports use the same filtered database records.

The Supabase secret key and advertising credentials exist only in GitHub Actions secrets.
The browser never receives advertising access tokens or the Supabase secret key.

## Refresh policy

- Hourly: current day plus the previous seven days.
- Nightly: previous 30 days to capture attribution changes.
- Quarter close: reconcile the full quarter and record the successful sync run.
- Upserts use `(ad_account_id, external_campaign_id, metric_date)` as the natural key.

## Current phases

- Phase 1: schema, canonical records, currency handling, security and tests.
- Phase 2: Supabase writer and Meta daily campaign collector.
- Phase 3: TikTok and Google Ads daily campaign collectors.
- Phase 4: GA4, website and Steam product metrics.
- Phase 5: dashboard binding, authentication and automated report exports.
- Phase 6: Bluehost deployment and operational monitoring.
