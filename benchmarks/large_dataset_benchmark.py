"""Reproducible large-CSV benchmark for the research artifact auditor.

Run on a Linux host for comparable peak-RSS readings:
  python benchmarks/large_dataset_benchmark.py --rows 100000 --symbols 100
  python benchmarks/large_dataset_benchmark.py --rows 1000000 --symbols 10000

The benchmark generates synthetic data; it is not a vendor-feed quality test.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import resource
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = (
    "datetime", "open", "high", "low", "close", "volume", "oi",
    "name", "symbol", "strike", "expiry", "contract_type", "side",
)


def peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports KiB; macOS reports bytes.
    return int(value if sys.platform == "darwin" else value * 1024)


def generate_csv(path: Path, rows: int, symbols: int, informational: bool) -> None:
    if rows < 1 or symbols < 1:
        raise ValueError("rows and symbols must both be positive")
    start = datetime(2026, 1, 1)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for index in range(rows):
            symbol_id = index % symbols
            sequence = index // symbols
            # Inject a duplicate at every fifth observation for each symbol.
            # This exercises duplicate detection across all configured symbols.
            timestamp_sequence = sequence - 1 if sequence > 0 and sequence % 5 == 0 else sequence
            timestamp = (start + timedelta(seconds=timestamp_sequence)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            volume = "0" if informational else "10"
            oi = "0" if informational else "100"
            writer.writerow((
                timestamp, "100", "105", "95", "102", volume, oi,
                "SYNTH", f"SYM{symbol_id:08d}", "100", "2027-12-28", "OPT", "CE",
            ))


def worker_audit(path: Path) -> dict[str, object]:
    from src.artifact_auditor import audit_csv

    started = time.perf_counter()
    report = audit_csv(path, single_contract_file=False)
    serialized = json.dumps(report, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "mode": "audit",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "peak_rss_bytes": peak_rss_bytes(),
        "rows_read": report["counts"]["rows_read"],
        "issues": len(report["issues"]),
        "report_json_bytes": len(serialized),
        "errors": report["counts"]["errors"],
        "warnings": report["counts"]["warnings"],
        "info": report["counts"]["info"],
        "status": report["status"],
    }


def worker_keys(path: Path, strategy: str) -> dict[str, object]:
    started = time.perf_counter()
    total = 0
    duplicates = 0
    db_path: str | None = None
    connection: sqlite3.Connection | None = None
    keys: set[tuple[str, str]] | None = None

    if strategy == "ram":
        keys = set()
    else:
        fd, db_path = tempfile.mkstemp(prefix="auditor-keys-", suffix=".sqlite")
        os.close(fd)
        connection = sqlite3.connect(db_path)
        connection.execute(
            "CREATE TABLE seen (symbol TEXT NOT NULL, timestamp TEXT NOT NULL, "
            "PRIMARY KEY (symbol, timestamp)) WITHOUT ROWID"
        )

    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                total += 1
                key = (row["symbol"], row["datetime"])
                if keys is not None:
                    if key in keys:
                        duplicates += 1
                    else:
                        keys.add(key)
                else:
                    assert connection is not None
                    cursor = connection.execute(
                        "INSERT OR IGNORE INTO seen(symbol, timestamp) VALUES (?, ?)", key
                    )
                    if cursor.rowcount == 0:
                        duplicates += 1
            if connection is not None:
                connection.commit()
        disk_bytes = os.path.getsize(db_path) if db_path else 0
        return {
            "mode": f"duplicate_keys_{strategy}",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "peak_rss_bytes": peak_rss_bytes(),
            "rows_scanned": total,
            "unique_keys": total - duplicates,
            "duplicates": duplicates,
            "temporary_database_bytes": disk_bytes,
        }
    finally:
        if connection is not None:
            connection.close()
        if db_path and os.path.exists(db_path):
            os.unlink(db_path)


def worker(mode: str, path: Path) -> dict[str, object]:
    if mode == "audit":
        return worker_audit(path)
    if mode in {"ram", "sqlite"}:
        return worker_keys(path, mode)
    raise ValueError(f"Unknown worker mode: {mode}")


def run_isolated(mode: str, path: Path) -> dict[str, object]:
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", mode, str(path)]
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(ROOT) if not existing_pythonpath
        else str(ROOT) + os.pathsep + existing_pythonpath
    )
    result = subprocess.run(
        command, cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise RuntimeError(
            f"{mode} worker failed (exit {result.returncode}): {result.stderr[-4000:]}"
        )
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--symbols", type=int, default=100)
    parser.add_argument(
        "--informational", action="store_true",
        help="Set volume and OI to zero to measure repeated INFO issue growth.",
    )
    parser.add_argument("--worker", choices=("audit", "ram", "sqlite"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("worker_path", nargs="?", type=Path)
    args = parser.parse_args()

    if args.worker:
        path = args.worker_path or args.input
        if path is None:
            parser.error("worker mode requires a CSV path")
        print(json.dumps(worker(args.worker, path), separators=(",", ":")))
        return 0

    with tempfile.TemporaryDirectory(prefix="auditor-benchmark-") as directory:
        csv_path = Path(directory) / "synthetic.csv"
        generate_csv(csv_path, args.rows, args.symbols, args.informational)
        results = [
            run_isolated(mode, csv_path) for mode in ("audit", "ram", "sqlite")
        ]
        print(json.dumps({
            "dataset": {
                "rows": args.rows,
                "symbols": args.symbols,
                "informational_zero_volume_and_oi": args.informational,
                "csv_bytes": csv_path.stat().st_size,
                "synthetic": True,
            },
            "results": results,
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
