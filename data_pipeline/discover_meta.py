"""Print Meta ad accounts accessible to the configured token."""

from __future__ import annotations

import json
import os
import sys

from .collectors.meta_ads import discover_meta_ad_accounts


def main() -> int:
    try:
        accounts = discover_meta_ad_accounts(
            access_token=os.environ.get("META_ACCESS_TOKEN", ""),
            api_version=os.environ.get("META_GRAPH_API_VERSION", ""),
        )
        print(json.dumps({"accounts": accounts}, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"Meta account discovery failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
