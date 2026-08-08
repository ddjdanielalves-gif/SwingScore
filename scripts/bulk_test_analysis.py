"""Bulk-test every B3 ticker through the full analysis pipeline.

Writes one JSON line per ticker to a results file (resumable: skips tickers
already present). Run in background, then inspect failures.

Usage: python scripts/bulk_test_analysis.py [sample_every]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.services import analysis, market_data  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "bulk_test_results.jsonl"


def main() -> None:
    every = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    tickers = [c["ticker"] for c in market_data.B3_INDEX]
    sample = tickers[::every]

    done = set()
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["ticker"])

    todo = [t for t in sample if t not in done]
    print(f"total={len(tickers)} sample={len(sample)} todo={len(todo)}")
    if not todo:
        return

    db = SessionLocal()
    ok = fail = 0
    t0 = time.time()
    with OUT.open("a", encoding="utf-8") as fh:
        for i, tk in enumerate(todo, 1):
            started = time.time()
            try:
                snap = asyncio.run(analysis.run(tk, db, force_refresh=True))
                row = {"ticker": tk, "ok": True, "score": float(snap.swing_score)}
                ok += 1
            except Exception as exc:
                row = {"ticker": tk, "ok": False, "error": repr(exc)[:300]}
                fail += 1
            row["elapsed"] = round(time.time() - started, 1)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            if i % 20 == 0 or not row["ok"]:
                print(f"[{i}/{len(todo)}] {tk} ok={ok} fail={fail} ({row['elapsed']}s)",
                      flush=True)
            db.rollback()
    print(f"DONE ok={ok} fail={fail} elapsed={round(time.time()-t0)}s", flush=True)


if __name__ == "__main__":
    main()
