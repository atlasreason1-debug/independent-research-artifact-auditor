"""Scale and failure-mode tests for the CSV auditor.

These tests measure behavior without imposing flaky wall-clock or memory limits.
The printed measurements are diagnostic evidence from the CI runner.
"""
import csv
import tempfile
import time
import tracemalloc
from datetime import datetime, timedelta
import unittest
from pathlib import Path

from src.artifact_auditor import REQUIRED_COLUMNS, audit_csv


def make_row(symbol, timestamp, *, volume="1", oi="1"):
    values = {
        "datetime": timestamp,
        "open": "100", "high": "105", "low": "95", "close": "102",
        "volume": volume, "oi": oi, "name": "NIFTY", "symbol": symbol,
        "strike": "24000", "expiry": "2027-12-28",
        "contract_type": "OPT", "side": "CE",
    }
    return [values[name] for name in REQUIRED_COLUMNS]


def temporary_csv():
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", newline="", encoding="utf-8", delete=False
    )
    return handle, Path(handle.name)


class LargeDatasetReliabilityTests(unittest.TestCase):
    def test_duplicate_detection_across_many_symbols_at_scale(self):
        handle, path = temporary_csv()
        symbol_count = 200
        timestamps_per_symbol = 100
        expected_rows = symbol_count * (timestamps_per_symbol + 1)
        try:
            writer = csv.writer(handle)
            writer.writerow(REQUIRED_COLUMNS)
            for symbol_index in range(symbol_count):
                symbol = f"NIFTY_TEST_{symbol_index:04d}"
                for minute in range(timestamps_per_symbol):
                    timestamp = (datetime(2026, 7, 17, 9, 0) + timedelta(minutes=minute)).strftime("%Y-%m-%d %H:%M:%S")
                    writer.writerow(make_row(symbol, timestamp))
                # Repeat the first timestamp after later timestamps for this symbol.
                writer.writerow(make_row(symbol, "2026-07-17 09:00:00"))
            handle.close()

            tracemalloc.start()
            started = time.perf_counter()
            report = audit_csv(path, single_contract_file=False)
            elapsed = time.perf_counter() - started
            _, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            duplicate_count = sum(
                issue["code"] == "DUPLICATE_CONTRACT_TIMESTAMP"
                for issue in report["issues"]
            )
            self.assertEqual(report["counts"]["rows_read"], expected_rows)
            self.assertEqual(duplicate_count, symbol_count)
            self.assertEqual(report["status"], "INVALID")
            print(
                "LARGE_DATASET_METRICS "
                f"rows={expected_rows} symbols={symbol_count} "
                f"elapsed_seconds={elapsed:.3f} "
                f"tracemalloc_peak_mb={peak_bytes / (1024 * 1024):.2f} "
                f"issue_count={len(report['issues'])}"
            )
        finally:
            if not handle.closed:
                handle.close()
            path.unlink(missing_ok=True)

    def test_repeated_zero_volume_and_oi_findings_are_counted_explicitly(self):
        handle, path = temporary_csv()
        row_count = 1000
        try:
            writer = csv.writer(handle)
            writer.writerow(REQUIRED_COLUMNS)
            for minute in range(row_count):
                writer.writerow(make_row(
                    "NIFTY_ZERO_TEST",
                    (datetime(2026, 7, 17, 9, 0) + timedelta(minutes=minute)).strftime("%Y-%m-%d %H:%M:%S"),
                    volume="0",
                    oi="0",
                ))
            handle.close()

            report = audit_csv(path, single_contract_file=False)
            zero_volume = sum(issue["code"] == "ZERO_VOLUME" for issue in report["issues"])
            zero_oi = sum(issue["code"] == "ZERO_OPEN_INTEREST" for issue in report["issues"])
            self.assertEqual(report["counts"]["rows_read"], row_count)
            self.assertEqual(zero_volume, row_count)
            self.assertEqual(zero_oi, row_count)
            self.assertEqual(len(report["issues"]), row_count * 2)
        finally:
            if not handle.closed:
                handle.close()
            path.unlink(missing_ok=True)

    def test_malformed_csv_at_eof_preserves_rows_already_read(self):
        handle, path = temporary_csv()
        try:
            writer = csv.writer(handle)
            writer.writerow(REQUIRED_COLUMNS)
            for minute in range(5):
                writer.writerow(make_row(
                    "NIFTY_PARSE_TEST",
                    f"2026-07-17 09:0{minute}:00",
                ))
            handle.write('"unterminated field')
            handle.close()

            report = audit_csv(path, single_contract_file=False)
            self.assertEqual(report["counts"]["rows_read"], 5)
            self.assertIn("CSV_PARSE_ERROR", {issue["code"] for issue in report["issues"]})
            self.assertEqual(report["status"], "INVALID")
        finally:
            if not handle.closed:
                handle.close()
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
