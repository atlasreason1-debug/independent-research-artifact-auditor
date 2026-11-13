"""Download and smoke-test one vendor-published real options session.

The ZIP is downloaded to a temporary directory and is never committed or uploaded.
Only a compact audit summary is retained as a GitHub Actions artifact.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
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
    "transactions", "multileg_volume", "active_minutes", "last_trade_date",
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


def run_vendor_verifier(archive_path: Path, extraction_root: Path) -> dict[str, Any]:
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise RuntimeError(f"Unsafe path in vendor archive: {name}")
        verifier_names = [name for name in names if name.endswith("/verify.py") or name == "verify.py"]
        if len(verifier_names) != 1:
            raise RuntimeError(f"Expected one vendor verify.py; found {len(verifier_names)}")
        archive.extractall(extraction_root)
        verifier_path = extraction_root / verifier_names[0]
        working_directory = verifier_path.parent
        command = [
            sys.executable,
            str(verifier_path),
            "--complete",
            "day_by_date",
        ]
        completed = subprocess.run(
            command,
            cwd=working_directory,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        return {
            "command": "python verify.py --complete day_by_date",
            "return_code": completed.returncode,
            "passed": completed.returncode == 0,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-2000:],
        }


def normalize_session(source_path: Path, full_path: Path, traded_path: Path) -> dict[str, Any]:
    rows_total = 0
    rows_with_complete_ohlc = 0
    missing_ohlc = {name: 0 for name in OHLC_COLUMNS}
    missing_ohlc_patterns: dict[str, int] = {}
    missing_ohlc_activity_patterns: dict[str, int] = {}
    missing_ohlc_activity_examples: list[dict[str, str]] = []
    missing_ohlc_by_volume = {"zero": 0, "positive": 0, "other_or_blank": 0}
    missing_ohlc_by_transactions = {"zero": 0, "positive": 0, "other_or_blank": 0}
    missing_ohlc_by_multileg_volume = {"zero": 0, "positive": 0, "other_or_blank": 0}
    positive_volume_missing_ohlc_by_transactions = {
        "zero": 0, "positive": 0, "other_or_blank": 0
    }

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
            transactions = (row.get("transactions") or "").strip()
            multileg_volume = (row.get("multileg_volume") or "").strip()
            missing_fields = sorted(
                name for name in OHLC_COLUMNS if not (row.get(name) or "").strip()
            )
            if missing_fields:
                pattern = "|".join(missing_fields)
                missing_ohlc_patterns[pattern] = missing_ohlc_patterns.get(pattern, 0) + 1

            def bucket(value: str) -> str:
                if value == "0":
                    return "zero"
                if value.isdigit() and int(value) > 0:
                    return "positive"
                return "other_or_blank"

            if not has_complete_ohlc:
                activity_key = (
                    f"missing={ '|'.join(missing_fields) };"
                    f"volume={bucket(volume)};"
                    f"transactions={bucket(transactions)};"
                    f"multileg_volume={bucket(multileg_volume)}"
                )
                missing_ohlc_activity_patterns[activity_key] = (
                    missing_ohlc_activity_patterns.get(activity_key, 0) + 1
                )
                missing_ohlc_by_volume[bucket(volume)] += 1
                missing_ohlc_by_transactions[bucket(transactions)] += 1
                missing_ohlc_by_multileg_volume[bucket(multileg_volume)] += 1
                if bucket(volume) == "positive":
                    positive_volume_missing_ohlc_by_transactions[bucket(transactions)] += 1

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
                "transactions": transactions,
                "multileg_volume": multileg_volume,
                "active_minutes": (row.get("active_minutes") or "").strip(),
                "last_trade_date": (row.get("last_trade_date") or "").strip(),
            }
            if missing_fields and (bucket(volume) == "positive" or bucket(transactions) == "positive") and len(missing_ohlc_activity_examples) < 20:
                missing_ohlc_activity_examples.append({
                    "contract": (row.get("contract") or "").strip(),
                    "underlying": (row.get("underlying") or "").strip(),
                    "expiration": (row.get("expiration") or "").strip(),
                    "type": (row.get("type") or "").strip(),
                    "strike": (row.get("strike") or "").strip(),
                    "bid": (row.get("bid") or "").strip(),
                    "ask": (row.get("ask") or "").strip(),
                    "volume": volume,
                    "transactions": transactions,
                    "multileg_volume": multileg_volume,
                    "active_minutes": normalized["active_minutes"],
                    "last_trade_date": normalized["last_trade_date"],
                    "open": normalized["open"], "high": normalized["high"],
                    "low": normalized["low"], "close": normalized["close"],
                })
            full_writer.writerow(normalized)
            if has_complete_ohlc:
                traded_writer.writerow(normalized)
                rows_with_complete_ohlc += 1

    return {
        "rows_total": rows_total,
        "rows_with_complete_ohlc": rows_with_complete_ohlc,
        "rows_without_complete_ohlc": rows_total - rows_with_complete_ohlc,
        "missing_ohlc_cells": missing_ohlc,
        "missing_ohlc_field_patterns": dict(sorted(missing_ohlc_patterns.items())),
        "missing_ohlc_activity_patterns": dict(sorted(missing_ohlc_activity_patterns.items())),
        "missing_ohlc_activity_examples": missing_ohlc_activity_examples,
        "rows_without_complete_ohlc_by_volume": missing_ohlc_by_volume,
        "rows_without_complete_ohlc_by_transactions": missing_ohlc_by_transactions,
        "rows_without_complete_ohlc_by_multileg_volume": missing_ohlc_by_multileg_volume,
        "positive_volume_missing_ohlc_by_transactions": positive_volume_missing_ohlc_by_transactions,
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
        vendor_extract = root / "vendor_archive"
        vendor_extract.mkdir()
        full_path = root / "normalized_all_rows.csv"
        traded_path = root / "normalized_rows_with_ohlc.csv"

        download_sample(archive_path)
        source_metadata = extract_verified_session(archive_path, source_path)
        vendor_verifier = run_vendor_verifier(archive_path, vendor_extract)
        normalization = normalize_session(source_path, full_path, traded_path)

        results = {
            "vendor_verifier": vendor_verifier,
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
