-- Full-fidelity paid media history at campaign and ad grain.

alter table public.campaign_metrics_daily
    add column if not exists reach bigint not null default 0 check (reach >= 0),
    add column if not exists link_clicks bigint not null default 0 check (link_clicks >= 0),
    add column if not exists landing_page_views bigint not null default 0
        check (landing_page_views >= 0);

create table if not exists public.ad_entities (
    id bigint generated always as identity primary key,
    brand_id uuid not null references public.brands(id),
    ad_account_id uuid not null references public.ad_accounts(id),
    platform text not null,
    external_campaign_id text not null,
    campaign_name text not null,
    external_adset_id text not null,
    adset_name text not null,
    external_ad_id text not null,
    ad_name text not null,
    status text not null,
    effective_status text not null,
    creative_id text,
    created_time timestamptz,
    updated_time timestamptz,
    fetched_at timestamptz not null default now(),
    unique (ad_account_id, external_ad_id)
);

create index if not exists ad_entities_brand_idx
    on public.ad_entities (brand_id, external_ad_id);

create table if not exists public.ad_metrics_daily (
    id bigint generated always as identity primary key,
    brand_id uuid not null references public.brands(id),
    ad_account_id uuid not null references public.ad_accounts(id),
    platform text not null,
    external_campaign_id text not null,
    campaign_name text not null,
    external_adset_id text not null,
    adset_name text not null,
    external_ad_id text not null,
    ad_name text not null,
    metric_date date not null,
    spend_original numeric(20, 6) not null default 0 check (spend_original >= 0),
    original_currency char(3) not null check (original_currency ~ '^[A-Z]{3}$'),
    fx_to_usd numeric(20, 10) not null check (fx_to_usd > 0),
    spend_usd numeric(20, 6) not null default 0 check (spend_usd >= 0),
    impressions bigint not null default 0 check (impressions >= 0),
    reach bigint not null default 0 check (reach >= 0),
    clicks bigint not null default 0 check (clicks >= 0),
    link_clicks bigint not null default 0 check (link_clicks >= 0),
    landing_page_views bigint not null default 0 check (landing_page_views >= 0),
    conversions numeric(20, 6) not null default 0 check (conversions >= 0),
    conversion_value_usd numeric(20, 6) not null default 0
        check (conversion_value_usd >= 0),
    installs bigint not null default 0 check (installs >= 0),
    leads bigint not null default 0 check (leads >= 0),
    source_payload jsonb,
    sync_run_id uuid references public.sync_runs(id),
    fetched_at timestamptz not null default now(),
    unique (ad_account_id, external_ad_id, metric_date)
);

create index if not exists ad_metrics_brand_date_idx
    on public.ad_metrics_daily (brand_id, metric_date desc);
create index if not exists ad_metrics_campaign_date_idx
    on public.ad_metrics_daily (external_campaign_id, metric_date desc);
create index if not exists ad_metrics_ad_date_idx
    on public.ad_metrics_daily (external_ad_id, metric_date desc);

create or replace view public.ad_performance_weekly as
select
    b.slug as brand_slug,
    m.platform,
    a.external_account_id,
    m.external_campaign_id,
    m.campaign_name,
    m.external_adset_id,
    m.adset_name,
    m.external_ad_id,
    m.ad_name,
    date_trunc('week', m.metric_date)::date as week_start,
    sum(m.spend_usd) as spend_usd,
    sum(m.impressions) as impressions,
    sum(m.reach) as reach_daily_sum,
    sum(m.clicks) as clicks,
    sum(m.link_clicks) as link_clicks,
    sum(m.landing_page_views) as landing_page_views,
    sum(m.conversions) as conversions,
    sum(m.conversion_value_usd) as conversion_value_usd,
    sum(m.installs) as installs,
    sum(m.leads) as leads,
    case when sum(m.impressions) > 0
        then sum(m.clicks)::numeric / sum(m.impressions) end as ctr,
    case when sum(m.clicks) > 0
        then sum(m.spend_usd) / sum(m.clicks) end as cpc_usd,
    case when sum(m.impressions) > 0
        then sum(m.spend_usd) * 1000 / sum(m.impressions) end as cpm_usd,
    case when sum(m.installs) > 0
        then sum(m.spend_usd) / sum(m.installs) end as cpi_usd,
    case when sum(m.spend_usd) > 0
        then sum(m.conversion_value_usd) / sum(m.spend_usd) end as roas
from public.ad_metrics_daily m
join public.brands b on b.id = m.brand_id
join public.ad_accounts a on a.id = m.ad_account_id
group by
    b.slug, m.platform, a.external_account_id,
    m.external_campaign_id, m.campaign_name, m.external_adset_id, m.adset_name,
    m.external_ad_id, m.ad_name, date_trunc('week', m.metric_date);

create or replace view public.ad_performance_quarterly as
select
    b.slug as brand_slug,
    m.platform,
    a.external_account_id,
    m.external_campaign_id,
    m.campaign_name,
    m.external_adset_id,
    m.adset_name,
    m.external_ad_id,
    m.ad_name,
    date_trunc('quarter', m.metric_date)::date as quarter_start,
    sum(m.spend_usd) as spend_usd,
    sum(m.impressions) as impressions,
    sum(m.reach) as reach_daily_sum,
    sum(m.clicks) as clicks,
    sum(m.link_clicks) as link_clicks,
    sum(m.landing_page_views) as landing_page_views,
    sum(m.conversions) as conversions,
    sum(m.conversion_value_usd) as conversion_value_usd,
    sum(m.installs) as installs,
    sum(m.leads) as leads,
    case when sum(m.impressions) > 0
        then sum(m.clicks)::numeric / sum(m.impressions) end as ctr,
    case when sum(m.clicks) > 0
        then sum(m.spend_usd) / sum(m.clicks) end as cpc_usd,
    case when sum(m.impressions) > 0
        then sum(m.spend_usd) * 1000 / sum(m.impressions) end as cpm_usd,
    case when sum(m.installs) > 0
        then sum(m.spend_usd) / sum(m.installs) end as cpi_usd,
    case when sum(m.spend_usd) > 0
        then sum(m.conversion_value_usd) / sum(m.spend_usd) end as roas
from public.ad_metrics_daily m
join public.brands b on b.id = m.brand_id
join public.ad_accounts a on a.id = m.ad_account_id
group by
    b.slug, m.platform, a.external_account_id,
    m.external_campaign_id, m.campaign_name, m.external_adset_id, m.adset_name,
    m.external_ad_id, m.ad_name, date_trunc('quarter', m.metric_date);

create or replace view public.ad_performance_ytd as
select
    b.slug as brand_slug,
    m.platform,
    a.external_account_id,
    m.external_campaign_id,
    m.campaign_name,
    m.external_adset_id,
    m.adset_name,
    m.external_ad_id,
    m.ad_name,
    extract(year from m.metric_date)::integer as report_year,
    sum(m.spend_usd) as spend_usd,
    sum(m.impressions) as impressions,
    sum(m.reach) as reach_daily_sum,
    sum(m.clicks) as clicks,
    sum(m.link_clicks) as link_clicks,
    sum(m.landing_page_views) as landing_page_views,
    sum(m.conversions) as conversions,
    sum(m.conversion_value_usd) as conversion_value_usd,
    sum(m.installs) as installs,
    sum(m.leads) as leads,
    case when sum(m.impressions) > 0
        then sum(m.clicks)::numeric / sum(m.impressions) end as ctr,
    case when sum(m.clicks) > 0
        then sum(m.spend_usd) / sum(m.clicks) end as cpc_usd,
    case when sum(m.impressions) > 0
        then sum(m.spend_usd) * 1000 / sum(m.impressions) end as cpm_usd,
    case when sum(m.installs) > 0
        then sum(m.spend_usd) / sum(m.installs) end as cpi_usd,
    case when sum(m.spend_usd) > 0
        then sum(m.conversion_value_usd) / sum(m.spend_usd) end as roas
from public.ad_metrics_daily m
join public.brands b on b.id = m.brand_id
join public.ad_accounts a on a.id = m.ad_account_id
group by
    b.slug, m.platform, a.external_account_id,
    m.external_campaign_id, m.campaign_name, m.external_adset_id, m.adset_name,
    m.external_ad_id, m.ad_name, extract(year from m.metric_date);

alter table public.ad_metrics_daily enable row level security;
alter table public.ad_entities enable row level security;
drop policy if exists "authenticated users can read ad entities"
    on public.ad_entities;
create policy "authenticated users can read ad entities"
    on public.ad_entities for select to authenticated using (true);
drop policy if exists "authenticated users can read ad metrics"
    on public.ad_metrics_daily;
create policy "authenticated users can read ad metrics"
    on public.ad_metrics_daily for select to authenticated using (true);

revoke all on public.ad_metrics_daily from anon;
revoke all on public.ad_entities from anon;
grant select on public.ad_entities to authenticated;
grant select on public.ad_metrics_daily to authenticated;
grant select on public.ad_performance_weekly to authenticated;
grant select on public.ad_performance_quarterly to authenticated;
grant select on public.ad_performance_ytd to authenticated;
