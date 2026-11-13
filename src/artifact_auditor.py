"""Deterministic CSV integrity checks for OHLC/options research artifacts.

This module validates structure and row-level invariants. It does not certify
market-data authenticity, backtest validity, or strategy profitability.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import tempfile
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

REQUIRED_COLUMNS = (
    "datetime", "open", "high", "low", "close", "volume", "oi",
    "name", "symbol", "strike", "expiry", "contract_type", "side",
)
OHLC_COLUMNS = ("open", "high", "low", "close")
NUMERIC_COLUMNS = ("open", "high", "low", "close", "volume", "oi", "strike")
OPTIONAL_NUMERIC_COLUMNS = ("transactions", "multileg_volume")
NON_NEGATIVE_COLUMNS = ("open", "high", "low", "close", "volume", "oi", "strike")
CONTRACT_COLUMNS = ("name", "symbol", "strike", "expiry", "contract_type", "side")
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
NUMERIC_PATTERN = re.compile(
    r"^(?:[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?)|(?:\.[0-9]+))(?:[eE][+-]?[0-9]+)?"
    r"|[+-]?(?:s?nan|inf(?:inity)?))$",
    re.IGNORECASE,
)


def _issue(severity: str, code: str, message: str, row: int | None = None,
           column: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if row is not None:
        item["row"] = row
    if column is not None:
        item["column"] = column
    return item


def _parse_compact_option_symbol(
    name: str,
    symbol: str,
    metadata_expiry: str | None = None,
    metadata_strike: Decimal | None = None,
) -> tuple[str, Decimal, str] | None:
    """Parse known option symbol shapes, using metadata to disambiguate dates.

    Supported forms:
    - {name}{DDMMMYY}{strike}{CE|PE}
    - {name}{YYMMMDD}{strike}{CE|PE}
    - {name}{YYMMM}{strike}{CE|PE} (monthly; day is not encoded)

    The monthly form is compared at year-month precision because its symbol
    does not contain an expiry day. Unknown shapes remain ignored.
    """
    if not name or not symbol or len(symbol) <= len(name):
        return None
    if symbol[:len(name)].casefold() != name.casefold():
        return None

    suffix = symbol[len(name):]
    side = suffix[-2:].upper()
    if side not in {"CE", "PE"}:
        return None
    body = suffix[:-2]

    candidates: list[tuple[str, Decimal, str, str]] = []
    for prefix_length, date_format, kind in (
        (7, "%y%b%d", "weekly"),
        (7, "%d%b%y", "legacy"),
        (5, "%y%b", "monthly"),
    ):
        if len(body) <= prefix_length:
            continue
        date_text = body[:prefix_length].upper()
        strike_text = body[prefix_length:]
        if re.fullmatch(r"\d+(?:\.\d+)?", strike_text) is None:
            continue
        try:
            parsed_date = datetime.strptime(date_text, date_format).date()
            strike = Decimal(strike_text)
        except (ValueError, InvalidOperation):
            continue
        if not strike.is_finite():
            continue

        if kind == "monthly":
            year_month = parsed_date.strftime("%Y-%m")
            expiry = (
                metadata_expiry
                if metadata_expiry and metadata_expiry[:7] == year_month
                else f"{year_month}-01"
            )
        else:
            expiry = parsed_date.isoformat()
        candidates.append((expiry, strike, side, kind))

    if not candidates:
        return None

    def matches_metadata(candidate: tuple[str, Decimal, str, str]) -> bool:
        expiry, strike, _, kind = candidate
        if metadata_strike is not None and strike != metadata_strike:
            return False
        if metadata_expiry:
            if kind == "monthly":
                # Strike identifies the monthly form; compare its encoded year-month
                # separately so a wrong month is reported without inventing an expiry day.
                return True
            return expiry == metadata_expiry
        return metadata_strike is not None

    matching = [candidate for candidate in candidates if matches_metadata(candidate)]
    if matching:
        selected = next(
            (candidate for candidate in matching if candidate[3] != "monthly"),
            matching[0],
        )
    else:
        selected = next(
            (candidate for kind in ("legacy", "weekly", "monthly")
             for candidate in candidates if candidate[3] == kind),
            candidates[0],
        )

    expiry, strike, parsed_side, _ = selected
    return expiry, strike, parsed_side


class _DuplicateTracker:
    """Track symbol/timestamp keys in RAM or a temporary SQLite database."""

    def __init__(self, strategy: str) -> None:
        if strategy not in {"memory", "sqlite"}:
            raise ValueError("duplicate_store must be 'memory' or 'sqlite'")
        self._keys: set[tuple[str, str]] | None = set() if strategy == "memory" else None
        self._temporary_directory = None
        self._connection = None
        self._operations = 0
        if strategy == "sqlite":
            self._temporary_directory = tempfile.TemporaryDirectory(prefix="artifact-auditor-")
            try:
                database_path = Path(self._temporary_directory.name) / "seen.sqlite"
                self._connection = sqlite3.connect(database_path)
                self._connection.execute(
                    "CREATE TABLE seen (symbol TEXT NOT NULL, timestamp TEXT NOT NULL, "
                    "PRIMARY KEY (symbol, timestamp)) WITHOUT ROWID"
                )
            except BaseException:
                if self._connection is not None:
                    self._connection.close()
                    self._connection = None
                self._temporary_directory.cleanup()
                self._temporary_directory = None
                raise

    def __enter__(self) -> "_DuplicateTracker":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            if self._connection is not None:
                try:
                    if exc_type is None:
                        self._connection.commit()
                finally:
                    self._connection.close()
                    self._connection = None
        finally:
            if self._temporary_directory is not None:
                self._temporary_directory.cleanup()
                self._temporary_directory = None

    def is_duplicate(self, symbol: str, timestamp: str) -> bool:
        if self._keys is not None:
            key = (symbol, timestamp)
            if key in self._keys:
                return True
            self._keys.add(key)
            return False

        assert self._connection is not None
        cursor = self._connection.execute(
            "INSERT OR IGNORE INTO seen(symbol, timestamp) VALUES (?, ?)",
            (symbol, timestamp),
        )
        self._operations += 1
        # Bound SQLite's dirty-page cache and make the temporary store genuinely disk-backed.
        if self._operations % 10_000 == 0:
            self._connection.commit()
        return cursor.rowcount == 0


def _audit_csv_impl(
    path: str | Path,
    *,
    single_contract_file: bool,
    max_issues: int | None,
    duplicate_tracker: _DuplicateTracker,
) -> dict[str, Any]:
    """Audit a CSV file and return a JSON-serializable report.

    Row numbers in issues are physical CSV line numbers (header is line 1).
    Empty required cells receive one EMPTY_REQUIRED_VALUE issue and are not
    redundantly parsed as numeric/timestamp failures. OHLC values are conditionally
    available in options data, so their availability is summarized separately.
    """
    if max_issues is not None and max_issues < 0:
        raise ValueError("max_issues must be non-negative or None")

    file_path = Path(path)
    issues: list[dict[str, Any]] = []
    issue_counts = Counter()
    severity_counts = Counter()
    counts = {"rows_read": 0, "errors": 0, "warnings": 0, "info": 0}
    ohlc_rows_complete = 0
    ohlc_rows_partial = 0
    ohlc_rows_missing = 0
    ohlc_missing_cells = Counter()

    def record(item: dict[str, Any]) -> None:
        issue_counts[item["code"]] += 1
        severity_counts[item["severity"]] += 1
        if max_issues is None or len(issues) < max_issues:
            issues.append(item)

    def finish(status: str, columns: list[str] | None = None) -> dict[str, Any]:
        counts["errors"] = severity_counts["error"]
        counts["warnings"] = severity_counts["warning"]
        counts["info"] = severity_counts["info"]
        total_issues = sum(issue_counts.values())
        return {
            "file": str(file_path),
            "status": status,
            "mode": "single_contract" if single_contract_file else "multi_contract",
            "columns": columns or [],
            "counts": counts,
            "issues": issues,
            "issue_counts_by_code": dict(sorted(issue_counts.items())),
            "issues_truncated": total_issues > len(issues),
            "ohlc_availability": {
                "rows_with_all_fields": ohlc_rows_complete,
                "rows_with_partial_fields": ohlc_rows_partial,
                "rows_with_no_fields": ohlc_rows_missing,
                "missing_cells_by_column": dict(sorted(ohlc_missing_cells.items())),
            },
        }

    if not file_path.exists():
        record(_issue("error", "FILE_NOT_FOUND", f"File does not exist: {file_path}"))
        return finish("INVALID")
    if not file_path.is_file():
        record(_issue("error", "NOT_A_FILE", f"Path is not a regular file: {file_path}"))
        return finish("INVALID")

    try:
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            try:
                header = next(reader)
            except StopIteration:
                record(_issue("error", "EMPTY_FILE", "CSV file is empty."))
                return finish("INVALID")
            except csv.Error as exc:
                record(_issue("error", "CSV_PARSE_ERROR", f"Could not parse header: {exc}"))
                return finish("INVALID")

            columns = [cell.strip() for cell in header]
            if not columns or all(not cell for cell in columns):
                record(_issue("error", "EMPTY_HEADER", "CSV header is empty."))
                return finish("INVALID", columns)

            duplicates = sorted(name for name, count in Counter(columns).items() if name and count > 1)
            for name in duplicates:
                record(_issue("error", "DUPLICATE_HEADER", f"Header '{name}' occurs more than once.", column=name))
            if any(not name for name in columns):
                record(_issue("error", "EMPTY_HEADER_NAME", "One or more header names are empty."))

            missing = [name for name in REQUIRED_COLUMNS if name not in columns]
            for name in missing:
                record(_issue("error", "MISSING_REQUIRED_COLUMN", f"Required column '{name}' is missing.", column=name))

            if duplicates or any(not name for name in columns) or missing:
                return finish("INVALID", columns)

            index = {name: columns.index(name) for name in columns}
            max_timestamp_seen: dict[str, datetime] = {}
            reported_symbol_metadata: set[tuple[str, str, str]] = set()
            contract_values: dict[str, set[str]] = (
                {name: set() for name in CONTRACT_COLUMNS} if single_contract_file else {}
            )
            first_contract: dict[str, str] | None = None

            try:
                for row_values in reader:
                    physical_row = reader.line_num
                    if not row_values:
                        record(_issue("warning", "BLANK_ROW", "Blank CSV row skipped.", row=physical_row))
                        continue
                    counts["rows_read"] += 1
                    if len(row_values) > len(columns):
                        record(_issue("error", "EXTRA_FIELDS", f"Row has {len(row_values) - len(columns)} extra field(s).", row=physical_row))
                        row_values = row_values[:len(columns)]
                    if len(row_values) < len(columns):
                        record(_issue("error", "SHORT_ROW", f"Row has {len(columns) - len(row_values)} missing field(s).", row=physical_row))
                        row_values = row_values + [""] * (len(columns) - len(row_values))

                    values = {name: row_values[pos].strip() for name, pos in index.items()}
                    missing_ohlc = [name for name in OHLC_COLUMNS if not values[name]]
                    if not missing_ohlc:
                        ohlc_rows_complete += 1
                    elif len(missing_ohlc) == len(OHLC_COLUMNS):
                        ohlc_rows_missing += 1
                    else:
                        ohlc_rows_partial += 1
                    for name in missing_ohlc:
                        ohlc_missing_cells[name] += 1

                    empty_fields = [
                        name for name in REQUIRED_COLUMNS
                        if name not in OHLC_COLUMNS and not values[name]
                    ]
                    for name in empty_fields:
                        record(_issue("error", "EMPTY_REQUIRED_VALUE", f"Required value is empty in '{name}'.", row=physical_row, column=name))

                    numeric: dict[str, Decimal] = {}
                    for name in (*NUMERIC_COLUMNS, *OPTIONAL_NUMERIC_COLUMNS):
                        if name not in values:
                            continue
                        raw = values[name]
                        if not raw:
                            continue
                        if NUMERIC_PATTERN.fullmatch(raw) is None:
                            record(_issue("error", "INVALID_NUMERIC_VALUE", f"'{raw}' is not a valid number.", row=physical_row, column=name))
                            continue
                        try:
                            number = Decimal(raw)
                        except (InvalidOperation, ValueError):
                            record(_issue("error", "INVALID_NUMERIC_VALUE", f"'{raw}' is not a valid number.", row=physical_row, column=name))
                            continue
                        if not number.is_finite():
                            record(_issue("error", "NON_FINITE_VALUE", f"'{raw}' is not finite.", row=physical_row, column=name))
                            continue
                        numeric[name] = number
                        if name in NON_NEGATIVE_COLUMNS and number < Decimal(0):
                            record(_issue("error", "NEGATIVE_VALUE", f"'{name}' must be non-negative.", row=physical_row, column=name))

                    volume_value = numeric.get("volume")
                    transactions_value = numeric.get("transactions")
                    has_trade_activity = (
                        (volume_value is not None and volume_value > 0)
                        or (transactions_value is not None and transactions_value > 0)
                    )
                    if missing_ohlc:
                        if has_trade_activity:
                            record(_issue(
                                "warning",
                                "OHLC_UNAVAILABLE_WITH_ACTIVITY",
                                "One or more OHLC values are unavailable while trade activity is reported; this may reflect multi-leg or source-specific semantics and is not automatically invalid.",
                                row=physical_row,
                            ))
                        elif len(missing_ohlc) < len(OHLC_COLUMNS):
                            record(_issue(
                                "warning",
                                "PARTIAL_OHLC_FIELDS",
                                "Only some OHLC values are available; inspect the source's field-availability rules.",
                                row=physical_row,
                            ))

                    no_trade_evidence = (
                        volume_value == 0
                        and (transactions_value is None or transactions_value == 0)
                    )
                    if (
                        not no_trade_evidence
                        and all(name in numeric for name in OHLC_COLUMNS)
                    ):
                        o, h, low, c = (numeric[name] for name in OHLC_COLUMNS)
                        if h < max(o, low, c):
                            record(_issue("error", "INVALID_OHLC_HIGH", "high must be greater than or equal to open, low, and close.", row=physical_row, column="high"))
                        if low > min(o, h, c):
                            record(_issue("error", "INVALID_OHLC_LOW", "low must be less than or equal to open, high, and close.", row=physical_row, column="low"))

                    timestamp_text = values["datetime"]
                    parsed_timestamp = None
                    if timestamp_text:
                        try:
                            parsed_timestamp = datetime.strptime(timestamp_text, TIMESTAMP_FORMAT)
                            if parsed_timestamp.strftime(TIMESTAMP_FORMAT) != timestamp_text:
                                raise ValueError("timestamp is not in canonical YYYY-MM-DD HH:MM:SS format")
                        except ValueError:
                            record(_issue("error", "INVALID_TIMESTAMP", f"Timestamp '{timestamp_text}' must use YYYY-MM-DD HH:MM:SS.", row=physical_row, column="datetime"))

                    expiry_text = values["expiry"]
                    if expiry_text:
                        try:
                            parsed_expiry = date.fromisoformat(expiry_text)
                            if parsed_expiry.isoformat() != expiry_text:
                                raise ValueError("expiry is not canonical YYYY-MM-DD format")
                        except ValueError:
                            record(_issue(
                                "error", "INVALID_EXPIRY",
                                f"Expiry '{expiry_text}' must be a real calendar date in YYYY-MM-DD format.",
                                row=physical_row, column="expiry",
                            ))

                    if single_contract_file:
                        contract = {name: values[name] for name in CONTRACT_COLUMNS}
                        for name, value in contract.items():
                            if value:
                                contract_values[name].add(value)
                        if first_contract is None:
                            first_contract = contract
                        else:
                            for name, value in contract.items():
                                if value and first_contract.get(name) and value != first_contract[name]:
                                    # Report once per field, after all rows are processed.
                                    contract_values[name].add("__VARIATION__")

                    if values["side"] and values["side"] not in {"CE", "PE"}:
                        record(_issue("error", "INVALID_SIDE", "side must be CE or PE.", row=physical_row, column="side"))
                    if values["contract_type"] and values["contract_type"] not in {"OPT", "OPTIONS"}:
                        record(_issue("warning", "UNRECOGNIZED_CONTRACT_TYPE", "contract_type is not one of the recognized option labels OPT/OPTIONS.", row=physical_row, column="contract_type"))

                    parsed_symbol = _parse_compact_option_symbol(
                        values["name"],
                        values["symbol"],
                        values["expiry"],
                        numeric.get("strike"),
                    )
                    if parsed_symbol is not None:
                        symbol_expiry, symbol_strike, symbol_side = parsed_symbol
                        if values["expiry"] and values["expiry"] != symbol_expiry:
                            key = (values["symbol"], "expiry", values["expiry"])
                            if key not in reported_symbol_metadata:
                                record(_issue(
                                    "warning", "CONTRACT_SYMBOL_EXPIRY_MISMATCH",
                                    f"Symbol encodes expiry {symbol_expiry}, but metadata expiry is '{values['expiry']}'.",
                                    row=physical_row, column="expiry",
                                ))
                                reported_symbol_metadata.add(key)
                        metadata_strike = numeric.get("strike")
                        if metadata_strike is not None and metadata_strike != symbol_strike:
                                key = (values["symbol"], "strike", values["strike"])
                                if key not in reported_symbol_metadata:
                                    record(_issue(
                                        "warning", "CONTRACT_SYMBOL_STRIKE_MISMATCH",
                                        f"Symbol encodes strike {symbol_strike}, but metadata strike is '{values['strike']}'.",
                                        row=physical_row, column="strike",
                                    ))
                                    reported_symbol_metadata.add(key)
                        if values["side"] and values["side"].upper() != symbol_side:
                            key = (values["symbol"], "side", values["side"])
                            if key not in reported_symbol_metadata:
                                record(_issue(
                                    "warning", "CONTRACT_SYMBOL_SIDE_MISMATCH",
                                    f"Symbol encodes side {symbol_side}, but metadata side is '{values['side']}'.",
                                    row=physical_row, column="side",
                                ))
                                reported_symbol_metadata.add(key)

                    if parsed_timestamp is not None and values["symbol"]:
                        if duplicate_tracker.is_duplicate(values["symbol"], timestamp_text):
                            record(_issue("error", "DUPLICATE_CONTRACT_TIMESTAMP", "Duplicate timestamp for the same symbol.", row=physical_row, column="datetime"))
                        max_seen = max_timestamp_seen.get(values["symbol"])
                        if max_seen is not None and parsed_timestamp < max_seen:
                            record(_issue("warning", "NON_MONOTONIC_TIMESTAMP", "Timestamp is earlier than a timestamp already seen for this symbol.", row=physical_row, column="datetime"))
                        if max_seen is None or parsed_timestamp > max_seen:
                            max_timestamp_seen[values["symbol"]] = parsed_timestamp

                    if numeric.get("volume") == 0:
                        record(_issue("info", "ZERO_VOLUME", "Zero volume is informational and is not automatically invalid.", row=physical_row, column="volume"))
                    if numeric.get("oi") == 0:
                        record(_issue("info", "ZERO_OPEN_INTEREST", "Zero open interest may mean it was not reported; it is not automatically invalid.", row=physical_row, column="oi"))

            except csv.Error as exc:
                record(_issue("error", "CSV_PARSE_ERROR", f"CSV parsing failed near line {reader.line_num}: {exc}"))

            if counts["rows_read"] == 0:
                record(_issue("error", "NO_DATA_ROWS", "CSV contains a header but no data rows."))

            if single_contract_file:
                for name, values_seen in contract_values.items():
                    if "__VARIATION__" in values_seen:
                        record(_issue("warning", "CONTRACT_FIELD_VARIATION", f"'{name}' varies in a file configured as single-contract.", column=name))

            return finish("INVALID" if severity_counts["error"] else "VALID", columns)
    except (OSError, UnicodeError) as exc:
        record(_issue("error", "FILE_READ_ERROR", f"Could not read file: {exc}"))
        return finish("INVALID")



def audit_csv(
    path: str | Path,
    *,
    single_contract_file: bool = True,
    max_issues: int | None = None,
    duplicate_store: str = "memory",
) -> dict[str, Any]:
    """Audit a CSV, optionally using disk-backed duplicate-key tracking."""
    if max_issues is not None and max_issues < 0:
        raise ValueError("max_issues must be non-negative or None")
    with _DuplicateTracker(duplicate_store) as duplicate_tracker:
        return _audit_csv_impl(
            path,
            single_contract_file=single_contract_file,
            max_issues=max_issues,
            duplicate_tracker=duplicate_tracker,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a market-data CSV for structural and row-level integrity.")
    parser.add_argument("csv_file", help="Path to input CSV")
    parser.add_argument("--json", dest="json_path", help="Write JSON report to this path")
    parser.add_argument("--multi-contract", action="store_true", help="Disable single-contract field-variation warnings")
    parser.add_argument(
        "--max-issues", type=int, default=None,
        help="Limit detailed issue samples while preserving exact issue counts.",
    )
    parser.add_argument(
        "--duplicate-store", choices=("memory", "sqlite"), default="memory",
        help="Store duplicate keys in RAM (faster) or a temporary SQLite database (lower memory).",
    )
    args = parser.parse_args()

    report = audit_csv(
        args.csv_file,
        single_contract_file=not args.multi_contract,
        max_issues=args.max_issues,
        duplicate_store=args.duplicate_store,
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.json_path:
        Path(args.json_path).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 1 if report["status"] == "INVALID" else 0


if __name__ == "__main__":
    raise SystemExit(main())
