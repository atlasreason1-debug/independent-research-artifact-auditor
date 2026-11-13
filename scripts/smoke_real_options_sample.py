"""Download and smoke-test one vendor-published real options session.

The ZIP is downloaded to a temporary directory and is never committed or uploaded.
Only a compact audit summary is retained as a GitHub Actions artifact.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.artifact_auditor import audit_csv

SAMPLE_URL = "https://historicaldata.net/file/options_sample_2022H2.zip"
SAMPLE_ENTRY_SUFFIX = "day_by_date/2022-07-01_options.csv"
EXPECTED_SHA256 = "00a1c5086256ac6d66fc07f0045e755904fc240dbb29f90f9245ee5142c51ab2"
NORMALIZED_COLUMNS = (
    "datetime", "open", "high", "low", "close", "volume", "oi",
    "name", "symbol", "strike", "expiry", "contract_type", "side",
)
OHLC_COLUMNS = ("open", "high", "low", "close")


def download_sample(destination: Path) -> None:
    request = urllib.request.Request(
        SAMPLE_URL,
        headers={"User-Agent": "independent-research-artifact-auditor/real-data-smoke"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        with destination.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)


def extract_verified_session(archive_path: Path, destination: Path) -> dict[str, Any]:
    with zipfile.ZipFile(archive_path) as archive:
        matches = [
            name for name in archive.namelist()
            if name.replace("\\", "/").endswith(SAMPLE_ENTRY_SUFFIX)
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"Expected exactly one {SAMPLE_ENTRY_SUFFIX!r} entry; found {len(matches)}"
            )
        digest = hashlib.sha256()
        byte_count = 0
        with archive.open(matches[0]) as source, destination.open("wb") as output:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                byte_count += len(chunk)
                output.write(chunk)

    actual_sha256 = digest.hexdigest()
    if actual_sha256 != EXPECTED_SHA256:
        raise RuntimeError(
            f"Published sample checksum mismatch: expected {EXPECTED_SHA256}, got {actual_sha256}"
        )
    return {
        "archive_entry": matches[0],
        "sha256": actual_sha256,
        "bytes": byte_count,
    }


def normalize_session(source_path: Path, full_path: Path, traded_path: Path) -> dict[str, Any]:
    rows_total = 0
    rows_with_complete_ohlc = 0
    missing_ohlc = {name: 0 for name in OHLC_COLUMNS}
    missing_ohlc_by_volume = {"zero": 0, "positive": 0, "other_or_blank": 0}

    with (
        source_path.open("r", encoding="utf-8-sig", newline="") as source,
        full_path.open("w", encoding="utf-8", newline="") as full_handle,
        traded_path.open("w", encoding="utf-8", newline="") as traded_handle,
    ):
        reader = csv.DictReader(source)
        if reader.fieldnames is None:
            raise RuntimeError("Vendor sample has no CSV header")

        required_source = {
            "contract", "underlying", "expiration", "type", "strike",
            "quote_date", "volume", "open_interest", *OHLC_COLUMNS,
        }
        missing_columns = sorted(required_source.difference(reader.fieldnames))
        if missing_columns:
            raise RuntimeError(f"Vendor sample schema is missing columns: {missing_columns}")

        full_writer = csv.DictWriter(full_handle, fieldnames=NORMALIZED_COLUMNS)
        traded_writer = csv.DictWriter(traded_handle, fieldnames=NORMALIZED_COLUMNS)
        full_writer.writeheader()
        traded_writer.writeheader()

        for row in reader:
            rows_total += 1
            has_complete_ohlc = all((row.get(name) or "").strip() for name in OHLC_COLUMNS)
            for name in OHLC_COLUMNS:
                if not (row.get(name) or "").strip():
                    missing_ohlc[name] += 1

            volume = (row.get("volume") or "").strip()
            if not has_complete_ohlc:
                if volume == "0":
                    missing_ohlc_by_volume["zero"] += 1
                elif volume and volume.isdigit() and int(volume) > 0:
                    missing_ohlc_by_volume["positive"] += 1
                else:
                    missing_ohlc_by_volume["other_or_blank"] += 1

            option_type = (row.get("type") or "").strip().lower()
            side = {"call": "CE", "put": "PE"}.get(option_type, option_type.upper())
            quote_date = (row.get("quote_date") or "").strip()
            normalized = {
                "datetime": f"{quote_date} 00:00:00",
                "open": (row.get("open") or "").strip(),
                "high": (row.get("high") or "").strip(),
                "low": (row.get("low") or "").strip(),
                "close": (row.get("close") or "").strip(),
                "volume": volume,
                "oi": (row.get("open_interest") or "").strip(),
                "name": (row.get("underlying") or "").strip(),
                "symbol": (row.get("contract") or "").strip(),
                "strike": (row.get("strike") or "").strip(),
                "expiry": (row.get("expiration") or "").strip(),
                "contract_type": "OPT",
                "side": side,
            }
            full_writer.writerow(normalized)
            if has_complete_ohlc:
                traded_writer.writerow(normalized)
                rows_with_complete_ohlc += 1

    return {
        "rows_total": rows_total,
        "rows_with_complete_ohlc": rows_with_complete_ohlc,
        "rows_without_complete_ohlc": rows_total - rows_with_complete_ohlc,
        "missing_ohlc_cells": missing_ohlc,
        "rows_without_complete_ohlc_by_volume": missing_ohlc_by_volume,
    }


def compact_report(path: Path) -> dict[str, Any]:
    report = audit_csv(
        path,
        single_contract_file=False,
        max_issues=1000,
        duplicate_store="sqlite",
    )
    return {
        "status": report["status"],
        "rows_read": report["counts"]["rows_read"],
        "errors": report["counts"]["errors"],
        "warnings": report["counts"]["warnings"],
        "info": report["counts"]["info"],
        "sampled_issues": len(report["issues"]),
        "issues_truncated": report["issues_truncated"],
        "issue_counts_by_code": report["issue_counts_by_code"],
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="real-options-smoke-") as temporary:
        root = Path(temporary)
        archive_path = root / "options_sample.zip"
        source_path = root / "2022-07-01_options.csv"
        full_path = root / "normalized_all_rows.csv"
        traded_path = root / "normalized_rows_with_ohlc.csv"

        download_sample(archive_path)
        source_metadata = extract_verified_session(archive_path, source_path)
        normalization = normalize_session(source_path, full_path, traded_path)

        results = {
            "source": "HistoricalData.net free options sample",
            "source_url": SAMPLE_URL,
            "sample_session": "2022-07-01",
            "source_file": source_metadata,
            "normalization": normalization,
            "audit_all_rows": compact_report(full_path),
            "audit_rows_with_complete_ohlc": compact_report(traded_path),
            "interpretation": (
                "The all-rows audit deliberately preserves blank OHLC fields. "
                "The filtered audit is a diagnostic subset, not a replacement for "
                "the complete dataset. A blank trade field must be interpreted using "
                "the vendor's field definitions and trading-activity semantics."
            ),
            "raw_vendor_data_retained": False,
        }
        print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
