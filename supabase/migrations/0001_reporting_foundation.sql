-- Marketing Dashboard reporting foundation
-- Daily grain is authoritative. Weekly, quarterly and YTD figures are views.

create extension if not exists pgcrypto;

create table if not exists public.brands (
    id uuid primary key default gen_random_uuid(),
    slug text not null unique check (slug ~ '^[a-z0-9-]+$'),
    name text not null,
    timezone text not null default 'Asia/Riyadh',
    active boolean not null default true,
    created_at timestamptz not null default now()
);

insert into public.brands (slug, name)
values ('samla', 'SAMLA'), ('jackaroo-strike', 'Jackaroo Strike')
on conflict (slug) do update set name = excluded.name;

create table if not exists public.ad_accounts (
    id uuid primary key default gen_random_uuid(),
    brand_id uuid not null references public.brands(id),
    platform text not null check (
        platform in ('meta_ads', 'tiktok_ads', 'google_ads', 'snapchat_ads', 'linkedin_ads')
    ),
    external_account_id text not null,
    display_name text not null,
    account_currency char(3) not null check (account_currency ~ '^[A-Z]{3}$'),
    active boolean not null default true,
    created_at timestamptz not null default now(),
    unique (platform, external_account_id)
);

create table if not exists public.fx_rates_daily (
    rate_date date not null,
    source_currency char(3) not null check (source_currency ~ '^[A-Z]{3}$'),
    quote_currency char(3) not null default 'USD' check (quote_currency = 'USD'),
    rate numeric(20, 10) not null check (rate > 0),
    source text not null,
    fetched_at timestamptz not null default now(),
    primary key (rate_date, source_currency, quote_currency)
);

create table if not exists public.sync_runs (
    id uuid primary key default gen_random_uuid(),
    platform text not null,
    brand_id uuid references public.brands(id),
    requested_start date,
    requested_end date,
    status text not null check (status in ('running', 'succeeded', 'partial', 'failed')),
    rows_received integer not null default 0 check (rows_received >= 0),
    rows_written integer not null default 0 check (rows_written >= 0),
    error_summary text,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    constraint sync_date_order check (
        requested_start is null or requested_end is null or requested_start <= requested_end
    )
);

create table if not exists public.campaign_metrics_daily (
    id bigint generated always as identity primary key,
    brand_id uuid not null references public.brands(id),
    ad_account_id uuid not null references public.ad_accounts(id),
    platform text not null,
    external_campaign_id text not null,
    campaign_name text not null,
    metric_date date not null,
    spend_original numeric(20, 6) not null default 0 check (spend_original >= 0),
    original_currency char(3) not null check (original_currency ~ '^[A-Z]{3}$'),
    fx_to_usd numeric(20, 10) not null check (fx_to_usd > 0),
    spend_usd numeric(20, 6) not null default 0 check (spend_usd >= 0),
    impressions bigint not null default 0 check (impressions >= 0),
    clicks bigint not null default 0 check (clicks >= 0),
    conversions numeric(20, 6) not null default 0 check (conversions >= 0),
    conversion_value_usd numeric(20, 6) not null default 0 check (conversion_value_usd >= 0),
    installs bigint not null default 0 check (installs >= 0),
    leads bigint not null default 0 check (leads >= 0),
    source_payload jsonb,
    sync_run_id uuid references public.sync_runs(id),
    fetched_at timestamptz not null default now(),
    unique (ad_account_id, external_campaign_id, metric_date)
);

create index if not exists campaign_metrics_brand_date_idx
    on public.campaign_metrics_daily (brand_id, metric_date desc);
create index if not exists campaign_metrics_platform_date_idx
    on public.campaign_metrics_daily (platform, metric_date desc);

create table if not exists public.web_metrics_daily (
    id bigint generated always as identity primary key,
    brand_id uuid not null references public.brands(id),
    source text not null check (source in ('ga4', 'website', 'steam')),
    external_property_id text not null,
    metric_date date not null,
    sessions bigint check (sessions is null or sessions >= 0),
    users bigint check (users is null or users >= 0),
    new_users bigint check (new_users is null or new_users >= 0),
    pageviews bigint check (pageviews is null or pageviews >= 0),
    engaged_sessions bigint check (engaged_sessions is null or engaged_sessions >= 0),
    conversions numeric(20, 6) check (conversions is null or conversions >= 0),
    source_payload jsonb,
    fetched_at timestamptz not null default now(),
    unique (brand_id, source, external_property_id, metric_date)
);

create table if not exists public.product_metrics_daily (
    id bigint generated always as identity primary key,
    brand_id uuid not null references public.brands(id),
    source text not null check (source in ('steam', 'google_play', 'app_store')),
    external_product_id text not null,
    metric_date date not null,
    metric_name text not null,
    metric_value numeric(24, 6),
    unit text not null default 'count',
    source_payload jsonb,
    fetched_at timestamptz not null default now(),
    unique (brand_id, source, external_product_id, metric_date, metric_name)
);

create or replace view public.campaign_performance_weekly as
select
    b.slug as brand_slug,
    m.platform,
    date_trunc('week', m.metric_date)::date as week_start,
    sum(m.spend_usd) as spend_usd,
    sum(m.impressions) as impressions,
    sum(m.clicks) as clicks,
    sum(m.conversions) as conversions,
    sum(m.conversion_value_usd) as conversion_value_usd,
    sum(m.installs) as installs,
    sum(m.leads) as leads,
    case when sum(m.impressions) > 0 then sum(m.clicks)::numeric / sum(m.impressions) end as ctr,
    case when sum(m.clicks) > 0 then sum(m.spend_usd) / sum(m.clicks) end as cpc_usd,
    case when sum(m.installs) > 0 then sum(m.spend_usd) / sum(m.installs) end as cpi_usd,
    case when sum(m.spend_usd) > 0 then sum(m.conversion_value_usd) / sum(m.spend_usd) end as roas
from public.campaign_metrics_daily m
join public.brands b on b.id = m.brand_id
group by b.slug, m.platform, date_trunc('week', m.metric_date);

create or replace view public.campaign_performance_quarterly as
select
    b.slug as brand_slug,
    m.platform,
    date_trunc('quarter', m.metric_date)::date as quarter_start,
    sum(m.spend_usd) as spend_usd,
    sum(m.impressions) as impressions,
    sum(m.clicks) as clicks,
    sum(m.conversions) as conversions,
    sum(m.conversion_value_usd) as conversion_value_usd,
    sum(m.installs) as installs,
    sum(m.leads) as leads,
    case when sum(m.impressions) > 0 then sum(m.clicks)::numeric / sum(m.impressions) end as ctr,
    case when sum(m.clicks) > 0 then sum(m.spend_usd) / sum(m.clicks) end as cpc_usd,
    case when sum(m.installs) > 0 then sum(m.spend_usd) / sum(m.installs) end as cpi_usd,
    case when sum(m.spend_usd) > 0 then sum(m.conversion_value_usd) / sum(m.spend_usd) end as roas
from public.campaign_metrics_daily m
join public.brands b on b.id = m.brand_id
group by b.slug, m.platform, date_trunc('quarter', m.metric_date);

create or replace view public.campaign_performance_ytd as
select
    b.slug as brand_slug,
    m.platform,
    extract(year from m.metric_date)::integer as report_year,
    sum(m.spend_usd) as spend_usd,
    sum(m.impressions) as impressions,
    sum(m.clicks) as clicks,
    sum(m.conversions) as conversions,
    sum(m.conversion_value_usd) as conversion_value_usd,
    sum(m.installs) as installs,
    sum(m.leads) as leads,
    case when sum(m.impressions) > 0 then sum(m.clicks)::numeric / sum(m.impressions) end as ctr,
    case when sum(m.clicks) > 0 then sum(m.spend_usd) / sum(m.clicks) end as cpc_usd,
    case when sum(m.installs) > 0 then sum(m.spend_usd) / sum(m.installs) end as cpi_usd,
    case when sum(m.spend_usd) > 0 then sum(m.conversion_value_usd) / sum(m.spend_usd) end as roas
from public.campaign_metrics_daily m
join public.brands b on b.id = m.brand_id
group by b.slug, m.platform, extract(year from m.metric_date);

alter table public.brands enable row level security;
alter table public.ad_accounts enable row level security;
alter table public.fx_rates_daily enable row level security;
alter table public.sync_runs enable row level security;
alter table public.campaign_metrics_daily enable row level security;
alter table public.web_metrics_daily enable row level security;
alter table public.product_metrics_daily enable row level security;

create policy "authenticated users can read brands"
    on public.brands for select to authenticated using (true);
create policy "authenticated users can read ad accounts"
    on public.ad_accounts for select to authenticated using (true);
create policy "authenticated users can read fx rates"
    on public.fx_rates_daily for select to authenticated using (true);
create policy "authenticated users can read sync runs"
    on public.sync_runs for select to authenticated using (true);
create policy "authenticated users can read campaign metrics"
    on public.campaign_metrics_daily for select to authenticated using (true);
create policy "authenticated users can read web metrics"
    on public.web_metrics_daily for select to authenticated using (true);
create policy "authenticated users can read product metrics"
    on public.product_metrics_daily for select to authenticated using (true);

revoke all on public.brands from anon;
revoke all on public.ad_accounts from anon;
revoke all on public.fx_rates_daily from anon;
revoke all on public.sync_runs from anon;
revoke all on public.campaign_metrics_daily from anon;
revoke all on public.web_metrics_daily from anon;
revoke all on public.product_metrics_daily from anon;

grant select on public.brands to authenticated;
grant select on public.ad_accounts to authenticated;
grant select on public.fx_rates_daily to authenticated;
grant select on public.sync_runs to authenticated;
grant select on public.campaign_metrics_daily to authenticated;
grant select on public.web_metrics_daily to authenticated;
grant select on public.product_metrics_daily to authenticated;
grant select on public.campaign_performance_weekly to authenticated;
grant select on public.campaign_performance_quarterly to authenticated;
grant select on public.campaign_performance_ytd to authenticated;
