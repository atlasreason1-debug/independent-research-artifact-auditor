"""Smoke-test the official NSE F&O UDiFF bhavcopy with real options rows."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import tempfile
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from src.artifact_auditor import audit_csv

TRADE_DATE = "2026-11-11"
FILENAME = f"BhavCopy_NSE_FO_0_0_0_{TRADE_DATE.replace('-', '')}_F_0000.csv.zip"
URLS = (
    f"https://archives.nseindia.com/content/fo/{FILENAME}",
    f"https://nsearchives.nseindia.com/content/fo/{FILENAME}",
)
NORMALIZED_COLUMNS = (
    "datetime", "open", "high", "low", "close", "volume", "oi",
    "name", "symbol", "strike", "expiry", "contract_type", "side",
    "source_instrument_type", "source_instrument_id",
)


def download_archive(destination: Path) -> str:
    errors = []
    for url in URLS:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/zip,application/octet-stream,*/*",
                "Referer": "https://www.nseindia.com/all-reports-derivatives",
                "User-Agent": "Mozilla/5.0 (compatible; IndependentResearchArtifactAuditor/0.3)",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                with destination.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
            return url
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    raise RuntimeError("Could not download official NSE UDiFF file: " + " | ".join(errors))


def normalize_date(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("empty date")
    if "T" in value:
        value = value.split("T", 1)[0]
    for pattern in ("%Y-%m-%d", "%d-%b-%Y", "%d-%b-%y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"unsupported date format: {value!r}")


def pick(row: dict[str, str], *names: str) -> str:
    lowered = {str(key).strip().lower(): value for key, value in row.items() if key is not None}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None:
            return str(value).strip()
    return ""


def compact_audit(path: Path) -> dict[str, Any]:
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
    with tempfile.TemporaryDirectory(prefix="nse-udiff-smoke-") as temporary:
        root = Path(temporary)
        archive_path = root / FILENAME
        normalized_path = root / "normalized_nse_options.csv"
        source_url = download_archive(archive_path)
        archive_bytes = archive_path.read_bytes()
        archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()

        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise RuntimeError(f"Expected one CSV in NSE ZIP; found {len(csv_names)}")
            csv_bytes = archive.read(csv_names[0])
            csv_sha256 = hashlib.sha256(csv_bytes).hexdigest()

        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig", errors="strict")))
        if not reader.fieldnames:
            raise RuntimeError("NSE UDiFF CSV has no header")
        headers = {name.strip().lower() for name in reader.fieldnames}

        required_groups = {
            "trade_date": ("trad_dt", "bizdt"),
            "segment": ("sgmt",),
            "underlying": ("tckrsymb",),
            "expiry": ("xprydt",),
            "strike": ("strkpric",),
            "side": ("optnTp".lower(), "option_typ", "option_type"),
            "open": ("opnpric", "open"),
            "high": ("hghpric", "high"),
            "low": ("lwpric", "low"),
            "close": ("clspric", "close"),
            "volume": ("ttltradgvol", "contracts"),
            "oi": ("opnintrst", "open_int"),
        }
        missing = [
            logical for logical, aliases in required_groups.items()
            if not any(alias.lower() in headers for alias in aliases)
        ]
        if missing:
            raise RuntimeError(f"NSE UDiFF schema missing required fields: {missing}")

        rows_total = 0
        option_rows = 0
        segment_counts: Counter[str] = Counter()
        instrument_type_counts: Counter[str] = Counter()
        zero_volume = 0
        positive_volume = 0
        zero_oi = 0
        missing_ohlc = Counter()
        with normalized_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=NORMALIZED_COLUMNS)
            writer.writeheader()
            for row in reader:
                rows_total += 1
                trade_date = normalize_date(pick(row, "TradDt", "BizDt"))
                segment = pick(row, "Sgmt", "SEGMENT").upper()
                segment_counts[segment] += 1
                if trade_date != TRADE_DATE:
                    raise RuntimeError(f"Unexpected trade date {trade_date}; expected {TRADE_DATE}")
                if segment != "FO":
                    raise RuntimeError(f"Unexpected segment {segment!r}; expected FO")

                side = pick(row, "OptnTp", "OPTION_TYP", "OPTION_TYPE").upper()
                if side not in {"CE", "PE"}:
                    continue

                instrument_type = pick(row, "FinInstrmTp", "INSTRUMENT").upper()
                instrument_type_counts[instrument_type or "UNSPECIFIED"] += 1
                underlying = pick(row, "TckrSymb", "SYMBOL")
                expiry = normalize_date(pick(row, "XpryDt", "EXPIRY_DT"))
                strike = pick(row, "StrkPric", "STRIKE_PR")
                symbol = pick(row, "FinInstrmNm", "FinInstrmId", "SYMBOL")
                if not symbol:
                    symbol = f"{underlying}|{expiry}|{strike}|{side}"

                values = {
                    "datetime": f"{trade_date} 00:00:00",
                    "open": pick(row, "OpnPric", "OPEN"),
                    "high": pick(row, "HghPric", "HIGH"),
                    "low": pick(row, "LwPric", "LOW"),
                    "close": pick(row, "ClsPric", "CLOSE"),
                    "volume": pick(row, "TtlTradgVol", "CONTRACTS"),
                    "oi": pick(row, "OpnIntrst", "OPEN_INT"),
                    "name": underlying,
                    "symbol": symbol,
                    "strike": strike,
                    "expiry": expiry,
                    "contract_type": "OPT",
                    "side": side,
                    "source_instrument_type": instrument_type,
                    "source_instrument_id": pick(row, "FinInstrmId"),
                }
                option_rows += 1
                if values["volume"] == "0":
                    zero_volume += 1
                elif values["volume"]:
                    positive_volume += 1
                if values["oi"] == "0":
                    zero_oi += 1
                for name in ("open", "high", "low", "close"):
                    if not values[name]:
                        missing_ohlc[name] += 1
                writer.writerow(values)

        if option_rows == 0:
            raise RuntimeError("No CE/PE option rows found in official NSE file")

        results = {
            "source": "National Stock Exchange of India — official F&O UDiFF Common Bhavcopy Final",
            "source_url": source_url,
            "trade_date": TRADE_DATE,
            "archive_filename": FILENAME,
            "archive_bytes": len(archive_bytes),
            "archive_sha256": archive_sha256,
            "csv_entry": csv_names[0],
            "csv_bytes": len(csv_bytes),
            "csv_sha256": csv_sha256,
            "source_headers": reader.fieldnames,
            "rows_total_in_source": rows_total,
            "option_rows_audited": option_rows,
            "segment_counts": dict(segment_counts),
            "option_instrument_type_counts": dict(instrument_type_counts),
            "zero_volume_option_rows": zero_volume,
            "positive_volume_option_rows": positive_volume,
            "zero_open_interest_option_rows": zero_oi,
            "missing_ohlc_cells": dict(missing_ohlc),
            "audit_all_option_rows": compact_audit(normalized_path),
            "raw_vendor_data_retained": False,
            "timestamp_note": "00:00:00 is a daily grouping key only; it is not an NSE event timestamp or inferred timezone.",
        }
        print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
