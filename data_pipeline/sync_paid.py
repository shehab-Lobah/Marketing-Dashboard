"""CLI entry point for bounded paid-media synchronization."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from .collectors.meta_ads import collect_meta_daily
from .settings import accounts_for_platform, load_account_mappings
from .supabase_writer import SupabaseWriter


def rolling_window(days: int, today: date | None = None) -> tuple[date, date]:
    if days < 1:
        raise ValueError("days must be positive")
    end = today or date.today()
    return end - timedelta(days=days - 1), end


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("meta",), default="meta")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and validate records without writing to Supabase",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).with_name(".env"))
        args = parse_args(argv)
        if bool(args.start) != bool(args.end):
            raise ValueError("--start and --end must be supplied together")
        start_date, end_date = (
            (args.start, args.end) if args.start else rolling_window(args.days)
        )
        if start_date > end_date:
            raise ValueError("start date must be on or before end date")

        mapping_path = os.environ.get(
            "BRAND_MAPPING_PATH",
            str(Path(__file__).with_name("brand_mapping.json")),
        )
        mappings = load_account_mappings(mapping_path)
        meta_accounts = accounts_for_platform(mappings, "meta_ads")
        if not meta_accounts:
            raise ValueError("No meta_ads accounts are configured")

        token = os.environ.get("META_ACCESS_TOKEN", "")
        version = os.environ.get("META_GRAPH_API_VERSION", "")
        records = []
        for mapping in meta_accounts:
            records.extend(
                collect_meta_daily(
                    mapping,
                    access_token=token,
                    api_version=version,
                    start_date=start_date,
                    end_date=end_date,
                )
            )

        if args.dry_run:
            print(
                f"Validated {len(records)} Meta daily campaign rows "
                f"for {start_date.isoformat()}..{end_date.isoformat()}"
            )
            return 0

        written = SupabaseWriter.from_environment().upsert_campaign_metrics(
            records, mappings
        )
        print(
            f"Upserted {written} Meta daily campaign rows "
            f"for {start_date.isoformat()}..{end_date.isoformat()}"
        )
        return 0
    except Exception as exc:  # the workflow needs a concise non-secret failure
        print(f"Paid-media sync failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

