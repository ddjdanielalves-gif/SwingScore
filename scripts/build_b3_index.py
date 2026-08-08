"""Build the local B3 ticker index from the public brapi catalog.

Fetches https://brapi.dev/api/v2/tickers (all pages), keeps active
stocks/units/ETFs/BDRs (excludes FIIs and other funds), normalizes the
ticker to the Yahoo form (adds ".SA") and writes backend/app/data/b3_tickers.json.

Usage: python scripts/build_b3_index.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

API = "https://brapi.dev/api/v2/tickers"
KEEP_SUBTYPES = {"stock", "unit", "etf", "bdr"}
OUT = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "b3_tickers.json"


def _get(params: str) -> dict:
    with urllib.request.urlopen(f"{API}?{params}", timeout=60) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    first = _get("limit=1000")
    pagination = first.get("pagination", {})
    total_pages = pagination.get("totalPages", 1)
    print(f"totalItems={pagination.get('totalItems')} totalPages={total_pages}")

    items: list[dict] = list(first.get("results", []))
    for page in range(1, total_pages + 1):
        if page == 1:
            continue
        try:
            data = _get(f"limit=1000&page={page}")
            items.extend(data.get("results", []))
        except Exception as exc:
            print(f"page {page} failed: {exc}")

    index: list[dict] = []
    seen: set[str] = set()
    for it in items:
        if not it.get("isActive", False):
            continue
        if it.get("assetType") not in ("stock", "fund", "bdr"):
            continue
        if it.get("subType") not in KEEP_SUBTYPES:
            continue
        sym = (it.get("symbol") or "").strip().upper()
        if not sym:
            continue
        if sym.startswith("$") or sym.endswith("F"):
            continue
        yahoo = f"{sym}.SA"
        if yahoo in seen:
            continue
        seen.add(yahoo)
        name = it.get("longName") or it.get("name") or sym
        index.append(
            {
                "ticker": yahoo,
                "name": name,
                "sector": it.get("sector"),
            }
        )

    index.sort(key=lambda x: x["ticker"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(index)} tickers -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
