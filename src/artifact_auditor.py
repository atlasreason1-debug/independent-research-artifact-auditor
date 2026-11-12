"""Deterministic CSV integrity checks for OHLC/options research artifacts.

This module validates structure and row-level invariants. It does not certify
market-data authenticity, backtest validity, or strategy profitability.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

REQUIRED_COLUMNS = (
    "datetime", "open", "high", "low", "close", "volume", "oi",
    "name", "symbol", "strike", "expiry", "contract_type", "side",
)
NUMERIC_COLUMNS = ("open", "high", "low", "close", "volume", "oi", "strike")
NON_NEGATIVE_COLUMNS = ("open", "high", "low", "close", "volume", "oi", "strike")
CONTRACT_COLUMNS = ("name", "symbol", "strike", "expiry", "contract_type", "side")
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _issue(severity: str, code: str, message: str, row: int | None = None,
           column: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if row is not None:
        item["row"] = row
    if column is not None:
        item["column"] = column
    return item


def _parse_compact_option_symbol(name: str, symbol: str) -> tuple[str, Decimal, str] | None:
    """Parse only the observed {name}{DDMMMYY}{strike}{CE|PE} symbol shape.

    Unknown symbol conventions are deliberately ignored rather than guessed.
    The returned expiry is ISO YYYY-MM-DD.
    """
    if not name or not symbol:
        return None
    pattern = re.compile(
        rf"^{re.escape(name)}(?P<expiry>\d{{2}}[A-Z]{{3}}\d{{2}})"
        rf"(?P<strike>\d+(?:\.\d+)?)(?P<side>CE|PE)$",
        re.IGNORECASE,
    )
    match = pattern.fullmatch(symbol)
    if match is None:
        return None
    try:
        expiry = datetime.strptime(match.group("expiry").upper(), "%d%b%y").date().isoformat()
        strike = Decimal(match.group("strike"))
    except (ValueError, InvalidOperation):
        return None
    if not strike.is_finite():
        return None
    return expiry, strike, match.group("side").upper()


def audit_csv(path: str | Path, *, single_contract_file: bool = True) -> dict[str, Any]:
    """Audit a CSV file and return a JSON-serializable report.

    Row numbers in issues are physical CSV line numbers (header is line 1).
    Empty required cells receive one EMPTY_REQUIRED_VALUE issue and are not
    redundantly parsed as numeric/timestamp failures.
    """
    file_path = Path(path)
    issues: list[dict[str, Any]] = []
    counts = {"rows_read": 0, "errors": 0, "warnings": 0, "info": 0}

    def finish(status: str, columns: list[str] | None = None) -> dict[str, Any]:
        counts["errors"] = sum(x["severity"] == "error" for x in issues)
        counts["warnings"] = sum(x["severity"] == "warning" for x in issues)
        counts["info"] = sum(x["severity"] == "info" for x in issues)
        return {
            "file": str(file_path),
            "status": status,
            "mode": "single_contract" if single_contract_file else "multi_contract",
            "columns": columns or [],
            "counts": counts,
            "issues": issues,
        }

    if not file_path.exists():
        issues.append(_issue("error", "FILE_NOT_FOUND", f"File does not exist: {file_path}"))
        return finish("INVALID")
    if not file_path.is_file():
        issues.append(_issue("error", "NOT_A_FILE", f"Path is not a regular file: {file_path}"))
        return finish("INVALID")

    try:
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            try:
                header = next(reader)
            except StopIteration:
                issues.append(_issue("error", "EMPTY_FILE", "CSV file is empty."))
                return finish("INVALID")
            except csv.Error as exc:
                issues.append(_issue("error", "CSV_PARSE_ERROR", f"Could not parse header: {exc}"))
                return finish("INVALID")

            columns = [cell.strip() for cell in header]
            if not columns or all(not cell for cell in columns):
                issues.append(_issue("error", "EMPTY_HEADER", "CSV header is empty."))
                return finish("INVALID", columns)

            duplicates = sorted(name for name, count in Counter(columns).items() if name and count > 1)
            for name in duplicates:
                issues.append(_issue("error", "DUPLICATE_HEADER", f"Header '{name}' occurs more than once.", column=name))
            if any(not name for name in columns):
                issues.append(_issue("error", "EMPTY_HEADER_NAME", "One or more header names are empty."))

            missing = [name for name in REQUIRED_COLUMNS if name not in columns]
            for name in missing:
                issues.append(_issue("error", "MISSING_REQUIRED_COLUMN", f"Required column '{name}' is missing.", column=name))

            if duplicates or any(not name for name in columns) or missing:
                return finish("INVALID", columns)

            index = {name: columns.index(name) for name in columns}
            seen: set[tuple[str, str]] = set()
            max_timestamp_seen: dict[str, datetime] = {}
            reported_symbol_metadata: set[tuple[str, str, str]] = set()
            contract_values: dict[str, set[str]] = {name: set() for name in CONTRACT_COLUMNS}
            first_contract: dict[str, str] | None = None

            try:
                for row_values in reader:
                    physical_row = reader.line_num
                    if not row_values:
                        issues.append(_issue("warning", "BLANK_ROW", "Blank CSV row skipped.", row=physical_row))
                        continue
                    counts["rows_read"] += 1
                    if len(row_values) > len(columns):
                        issues.append(_issue("error", "EXTRA_FIELDS", f"Row has {len(row_values) - len(columns)} extra field(s).", row=physical_row))
                        continue
                    if len(row_values) < len(columns):
                        issues.append(_issue("error", "SHORT_ROW", f"Row has {len(columns) - len(row_values)} missing field(s).", row=physical_row))
                        row_values = row_values + [""] * (len(columns) - len(row_values))

                    values = {name: row_values[pos].strip() for name, pos in index.items()}
                    empty_fields = [name for name in REQUIRED_COLUMNS if not values[name]]
                    for name in empty_fields:
                        issues.append(_issue("error", "EMPTY_REQUIRED_VALUE", f"Required value is empty in '{name}'.", row=physical_row, column=name))

                    numeric: dict[str, Decimal] = {}
                    for name in NUMERIC_COLUMNS:
                        raw = values[name]
                        if not raw:
                            continue
                        try:
                            number = Decimal(raw)
                        except (InvalidOperation, ValueError):
                            issues.append(_issue("error", "INVALID_NUMERIC_VALUE", f"'{raw}' is not a valid number.", row=physical_row, column=name))
                            continue
                        if not number.is_finite():
                            issues.append(_issue("error", "NON_FINITE_VALUE", f"'{raw}' is not finite.", row=physical_row, column=name))
                            continue
                        numeric[name] = number
                        if name in NON_NEGATIVE_COLUMNS and number < Decimal(0):
                            issues.append(_issue("error", "NEGATIVE_VALUE", f"'{name}' must be non-negative.", row=physical_row, column=name))

                    if all(name in numeric for name in ("open", "high", "low", "close")):
                        o, h, low, c = (numeric[name] for name in ("open", "high", "low", "close"))
                        if h < max(o, low, c):
                            issues.append(_issue("error", "INVALID_OHLC_HIGH", "high must be greater than or equal to open, low, and close.", row=physical_row, column="high"))
                        if low > min(o, h, c):
                            issues.append(_issue("error", "INVALID_OHLC_LOW", "low must be less than or equal to open, high, and close.", row=physical_row, column="low"))

                    timestamp_text = values["datetime"]
                    parsed_timestamp = None
                    if timestamp_text:
                        try:
                            parsed_timestamp = datetime.strptime(timestamp_text, TIMESTAMP_FORMAT)
                            if parsed_timestamp.strftime(TIMESTAMP_FORMAT) != timestamp_text:
                                raise ValueError("timestamp is not in canonical YYYY-MM-DD HH:MM:SS format")
                        except ValueError:
                            issues.append(_issue("error", "INVALID_TIMESTAMP", f"Timestamp '{timestamp_text}' must use YYYY-MM-DD HH:MM:SS.", row=physical_row, column="datetime"))

                    expiry_text = values["expiry"]
                    if expiry_text:
                        try:
                            parsed_expiry = date.fromisoformat(expiry_text)
                            if parsed_expiry.isoformat() != expiry_text:
                                raise ValueError("expiry is not canonical YYYY-MM-DD format")
                        except ValueError:
                            issues.append(_issue(
                                "error", "INVALID_EXPIRY",
                                f"Expiry '{expiry_text}' must be a real calendar date in YYYY-MM-DD format.",
                                row=physical_row, column="expiry",
                            ))

                    contract = {name: values[name] for name in CONTRACT_COLUMNS}
                    for name, value in contract.items():
                        if value:
                            contract_values[name].add(value)
                    if first_contract is None:
                        first_contract = contract
                    elif single_contract_file:
                        for name, value in contract.items():
                            if value and first_contract.get(name) and value != first_contract[name]:
                                # Report once per field, after all rows are processed.
                                contract_values[name].add("__VARIATION__")

                    if values["side"] and values["side"] not in {"CE", "PE"}:
                        issues.append(_issue("error", "INVALID_SIDE", "side must be CE or PE.", row=physical_row, column="side"))
                    if values["contract_type"] and values["contract_type"] not in {"OPT", "OPTIONS"}:
                        issues.append(_issue("warning", "UNRECOGNIZED_CONTRACT_TYPE", "contract_type is not one of the recognized option labels OPT/OPTIONS.", row=physical_row, column="contract_type"))

                    parsed_symbol = _parse_compact_option_symbol(values["name"], values["symbol"])
                    if parsed_symbol is not None:
                        symbol_expiry, symbol_strike, symbol_side = parsed_symbol
                        if values["expiry"] and values["expiry"] != symbol_expiry:
                            key = (values["symbol"], "expiry", values["expiry"])
                            if key not in reported_symbol_metadata:
                                issues.append(_issue(
                                    "warning", "CONTRACT_SYMBOL_EXPIRY_MISMATCH",
                                    f"Symbol encodes expiry {symbol_expiry}, but metadata expiry is '{values['expiry']}'.",
                                    row=physical_row, column="expiry",
                                ))
                                reported_symbol_metadata.add(key)
                        if values["strike"]:
                            try:
                                metadata_strike = Decimal(values["strike"])
                            except InvalidOperation:
                                metadata_strike = None
                            if metadata_strike is not None and metadata_strike.is_finite() and metadata_strike != symbol_strike:
                                key = (values["symbol"], "strike", values["strike"])
                                if key not in reported_symbol_metadata:
                                    issues.append(_issue(
                                        "warning", "CONTRACT_SYMBOL_STRIKE_MISMATCH",
                                        f"Symbol encodes strike {symbol_strike}, but metadata strike is '{values['strike']}'.",
                                        row=physical_row, column="strike",
                                    ))
                                    reported_symbol_metadata.add(key)
                        if values["side"] and values["side"].upper() != symbol_side:
                            key = (values["symbol"], "side", values["side"])
                            if key not in reported_symbol_metadata:
                                issues.append(_issue(
                                    "warning", "CONTRACT_SYMBOL_SIDE_MISMATCH",
                                    f"Symbol encodes side {symbol_side}, but metadata side is '{values['side']}'.",
                                    row=physical_row, column="side",
                                ))
                                reported_symbol_metadata.add(key)

                    if parsed_timestamp is not None and values["symbol"]:
                        key = (values["symbol"], timestamp_text)
                        if key in seen:
                            issues.append(_issue("error", "DUPLICATE_CONTRACT_TIMESTAMP", "Duplicate timestamp for the same symbol.", row=physical_row, column="datetime"))
                        seen.add(key)
                        max_seen = max_timestamp_seen.get(values["symbol"])
                        if max_seen is not None and parsed_timestamp < max_seen:
                            issues.append(_issue("warning", "NON_MONOTONIC_TIMESTAMP", "Timestamp is earlier than a timestamp already seen for this symbol.", row=physical_row, column="datetime"))
                        if max_seen is None or parsed_timestamp > max_seen:
                            max_timestamp_seen[values["symbol"]] = parsed_timestamp

                    if numeric.get("volume") == 0:
                        issues.append(_issue("info", "ZERO_VOLUME", "Zero volume is informational and is not automatically invalid.", row=physical_row, column="volume"))
                    if numeric.get("oi") == 0:
                        issues.append(_issue("info", "ZERO_OPEN_INTEREST", "Zero open interest may mean it was not reported; it is not automatically invalid.", row=physical_row, column="oi"))

            except csv.Error as exc:
                issues.append(_issue("error", "CSV_PARSE_ERROR", f"CSV parsing failed near line {reader.line_num}: {exc}"))

            if counts["rows_read"] == 0:
                issues.append(_issue("error", "NO_DATA_ROWS", "CSV contains a header but no data rows."))

            if single_contract_file:
                for name, values_seen in contract_values.items():
                    if "__VARIATION__" in values_seen:
                        issues.append(_issue("warning", "CONTRACT_FIELD_VARIATION", f"'{name}' varies in a file configured as single-contract.", column=name))

            return finish("INVALID" if any(x["severity"] == "error" for x in issues) else "VALID", columns)
    except (OSError, UnicodeError) as exc:
        issues.append(_issue("error", "FILE_READ_ERROR", f"Could not read file: {exc}"))
        return finish("INVALID")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a market-data CSV for structural and row-level integrity.")
    parser.add_argument("csv_file", help="Path to input CSV")
    parser.add_argument("--json", dest="json_path", help="Write JSON report to this path")
    parser.add_argument("--multi-contract", action="store_true", help="Disable single-contract field-variation warnings")
    args = parser.parse_args()

    report = audit_csv(args.csv_file, single_contract_file=not args.multi_contract)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.json_path:
        Path(args.json_path).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 1 if report["status"] == "INVALID" else 0


if __name__ == "__main__":
    raise SystemExit(main())
