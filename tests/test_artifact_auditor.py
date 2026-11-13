import csv
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from src.artifact_auditor import REQUIRED_COLUMNS, audit_csv


def write_csv(rows, headers=None):
    tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", newline="", encoding="utf-8", delete=False)
    writer = csv.writer(tmp)
    writer.writerow(headers or REQUIRED_COLUMNS)
    writer.writerows(rows)
    tmp.close()
    return Path(tmp.name)


def valid_row(**overrides):
    row = {
        "datetime": "2026-07-17 09:21:00",
        "open": "100", "high": "105", "low": "95", "close": "102",
        "volume": "0", "oi": "0", "name": "NIFTY", "symbol": "NIFTY_TEST",
        "strike": "24000", "expiry": "2027-12-28", "contract_type": "OPT", "side": "CE",
    }
    row.update(overrides)
    return [row[name] for name in REQUIRED_COLUMNS]


class AuditorTests(unittest.TestCase):
    def audit_rows(self, rows, headers=None, **kwargs):
        path = write_csv(rows, headers)
        try:
            return audit_csv(path, **kwargs)
        finally:
            path.unlink(missing_ok=True)

    def codes(self, report):
        return {issue["code"] for issue in report["issues"]}

    def test_valid_row_with_zero_volume_and_oi_is_valid(self):
        report = self.audit_rows([valid_row()])
        self.assertEqual(report["status"], "VALID")
        self.assertIn("ZERO_VOLUME", self.codes(report))
        self.assertIn("ZERO_OPEN_INTEREST", self.codes(report))

    def test_empty_required_numeric_value_has_no_duplicate_numeric_error(self):
        row = valid_row()
        row[REQUIRED_COLUMNS.index("volume")] = ""
        report = self.audit_rows([row])
        matching = [x for x in report["issues"] if x.get("column") == "volume"]
        self.assertEqual([x["code"] for x in matching], ["EMPTY_REQUIRED_VALUE"])

    def test_blank_ohlc_is_availability_not_required_value_error(self):
        row = valid_row(open="", high="", low="", close="", volume="0")
        report = self.audit_rows([row])
        self.assertEqual(report["status"], "VALID")
        self.assertNotIn("EMPTY_REQUIRED_VALUE", self.codes(report))
        self.assertEqual(report["ohlc_availability"]["rows_with_no_fields"], 1)
        self.assertEqual(
            report["ohlc_availability"]["missing_cells_by_column"],
            {"close": 1, "high": 1, "low": 1, "open": 1},
        )

    def test_partial_ohlc_is_reported_as_warning(self):
        row = valid_row(close="", volume="0")
        report = self.audit_rows([row])
        self.assertEqual(report["status"], "VALID")
        self.assertIn("PARTIAL_OHLC_FIELDS", self.codes(report))
        self.assertEqual(report["ohlc_availability"]["rows_with_partial_fields"], 1)

    def test_ohlc_unavailable_with_volume_is_warning_not_error(self):
        headers = REQUIRED_COLUMNS + ("transactions",)
        row = valid_row(open="", high="", low="", close="", volume="10") + [""]
        report = self.audit_rows([row], headers=headers)
        self.assertEqual(report["status"], "VALID")
        self.assertIn("OHLC_UNAVAILABLE_WITH_ACTIVITY", self.codes(report))
        self.assertNotIn("EMPTY_REQUIRED_VALUE", self.codes(report))

    def test_zero_volume_no_trade_row_skips_ohlc_consistency(self):
        headers = REQUIRED_COLUMNS + ("transactions",)
        row = valid_row(open="0", high="0", low="0", close="100", volume="0") + ["0"]
        report = self.audit_rows([row], headers=headers)
        self.assertEqual(report["status"], "VALID")
        self.assertNotIn("INVALID_OHLC_HIGH", self.codes(report))

    def test_zero_volume_with_positive_transactions_still_checks_ohlc(self):
        headers = REQUIRED_COLUMNS + ("transactions",)
        row = valid_row(open="0", high="0", low="0", close="100", volume="0") + ["1"]
        report = self.audit_rows([row], headers=headers)
        self.assertEqual(report["status"], "INVALID")
        self.assertIn("INVALID_OHLC_HIGH", self.codes(report))

    def test_nan_and_infinity_are_non_finite(self):
        row = valid_row(open="NaN", close="inf")
        report = self.audit_rows([row])
        self.assertEqual(sum(x["code"] == "NON_FINITE_VALUE" for x in report["issues"]), 2)

    def test_malformed_decimal_is_reported_without_crashing(self):
        report = self.audit_rows([valid_row(volume="not-a-number")])
        self.assertIn("INVALID_NUMERIC_VALUE", self.codes(report))
        self.assertEqual(report["status"], "INVALID")
    def test_numeric_separators_are_not_silently_accepted(self):
        for value in ("1_000", "1,000"):
            with self.subTest(value=value):
                report = self.audit_rows([valid_row(volume=value)])
                self.assertIn("INVALID_NUMERIC_VALUE", self.codes(report))
                self.assertEqual(report["status"], "INVALID")

    def test_scientific_notation_is_accepted(self):
        report = self.audit_rows([valid_row(open="+1e2", high="1.05E2", low=".95e2", close="102.0")])
        self.assertEqual(report["status"], "VALID")
        self.assertNotIn("INVALID_NUMERIC_VALUE", self.codes(report))

    def test_negative_volume_is_invalid(self):
        report = self.audit_rows([valid_row(volume="-1")])
        self.assertIn("NEGATIVE_VALUE", self.codes(report))

    def test_decimal_underflow_is_not_misclassified_as_zero(self):
        report = self.audit_rows([valid_row(
            open="1e-1000", high="2e-1000", low="5e-1001",
            close="15e-1001", volume="1e-1000",
        )])
        self.assertEqual(report["status"], "VALID")
        self.assertNotIn("ZERO_VOLUME", self.codes(report))

    def test_decimal_precision_is_preserved_for_ohlc_comparisons(self):
        report = self.audit_rows([valid_row(
            open="0.3000000000000000000001",
            high="0.3",
            low="0.2",
            close="0.25",
            volume="1",
        )])
        self.assertIn("INVALID_OHLC_HIGH", self.codes(report))

    def test_very_large_finite_decimal_is_not_float_overflow(self):
        report = self.audit_rows([valid_row(
            open="1e10000", high="2e10000", low="5e9999", close="15e9999",
        )])
        self.assertEqual(report["status"], "VALID")
        self.assertNotIn("NON_FINITE_VALUE", self.codes(report))

    def test_impossible_expiry_date_is_invalid(self):
        report = self.audit_rows([valid_row(expiry="2025-02-29")])
        self.assertIn("INVALID_EXPIRY", self.codes(report))

    def test_noncanonical_expiry_date_is_invalid(self):
        report = self.audit_rows([valid_row(expiry="2024-2-9")])
        self.assertIn("INVALID_EXPIRY", self.codes(report))

    def test_valid_leap_day_expiry_is_accepted(self):
        report = self.audit_rows([valid_row(expiry="2024-02-29")])
        self.assertNotIn("INVALID_EXPIRY", self.codes(report))

    def test_ohlc_high_boundary_is_valid(self):
        report = self.audit_rows([valid_row(open="10", high="10", low="10", close="10")])
        self.assertEqual(report["status"], "VALID")

    def test_invalid_high_and_low_are_reported(self):
        report = self.audit_rows([valid_row(open="11", high="10", low="12", close="11", volume="1")])
        self.assertIn("INVALID_OHLC_HIGH", self.codes(report))
        self.assertIn("INVALID_OHLC_LOW", self.codes(report))

    def test_duplicate_timestamp_same_symbol_is_invalid_for_each_store(self):
        for duplicate_store in ("memory", "sqlite"):
            with self.subTest(duplicate_store=duplicate_store):
                report = self.audit_rows(
                    [valid_row(), valid_row()], duplicate_store=duplicate_store
                )
                self.assertIn("DUPLICATE_CONTRACT_TIMESTAMP", self.codes(report))
                self.assertEqual(report["status"], "INVALID")

    def test_sqlite_and_memory_stores_produce_identical_reports(self):
        rows = [
            valid_row(datetime="2026-07-17 09:22:00"),
            valid_row(datetime="2026-07-17 09:21:00", volume="-1"),
            valid_row(datetime="2026-07-17 09:22:00"),
        ]
        path = write_csv(rows)
        try:
            memory_report = audit_csv(path, duplicate_store="memory")
            sqlite_report = audit_csv(path, duplicate_store="sqlite")
            self.assertEqual(sqlite_report, memory_report)
        finally:
            path.unlink(missing_ok=True)

    def test_sqlite_tracker_cleans_temporary_directory_when_initialization_fails(self):
        temporary_directory = mock.Mock()
        temporary_directory.name = "/tmp/artifact-auditor-test"
        with (
            mock.patch(
                "src.artifact_auditor.tempfile.TemporaryDirectory",
                return_value=temporary_directory,
            ),
            mock.patch(
                "src.artifact_auditor.sqlite3.connect",
                side_effect=OSError("simulated database creation failure"),
            ),
        ):
            with self.assertRaisesRegex(OSError, "simulated database creation failure"):
                self.audit_rows([valid_row()], duplicate_store="sqlite")
        temporary_directory.cleanup.assert_called_once()

    def test_timestamp_must_be_canonical(self):
        report = self.audit_rows([valid_row(datetime="2026-7-17 9:21:00")])
        self.assertIn("INVALID_TIMESTAMP", self.codes(report))

    def test_short_row_is_reported(self):
        row = valid_row()[:-1]
        report = self.audit_rows([row])
        self.assertIn("SHORT_ROW", self.codes(report))

    def test_extra_field_is_reported(self):
        row = valid_row() + ["EXTRA"]
        report = self.audit_rows([row])
        self.assertIn("EXTRA_FIELDS", self.codes(report))
    def test_extra_fields_do_not_hide_invalid_known_values(self):
        row = valid_row(volume="-3", expiry="2025-02-29") + ["EXTRA"]
        report = self.audit_rows([row])
        self.assertIn("EXTRA_FIELDS", self.codes(report))
        self.assertIn("NEGATIVE_VALUE", self.codes(report))
        self.assertIn("INVALID_EXPIRY", self.codes(report))
        self.assertEqual(report["status"], "INVALID")

    def test_duplicate_header_is_invalid(self):
        headers = list(REQUIRED_COLUMNS) + ["close"]
        row = valid_row() + ["102"]
        report = self.audit_rows([row], headers=headers)
        self.assertIn("DUPLICATE_HEADER", self.codes(report))

    def test_missing_required_header_is_invalid(self):
        headers = [x for x in REQUIRED_COLUMNS if x != "oi"]
        row = [v for i, v in enumerate(valid_row()) if REQUIRED_COLUMNS[i] != "oi"]
        report = self.audit_rows([row], headers=headers)
        self.assertIn("MISSING_REQUIRED_COLUMN", self.codes(report))

    def test_compact_symbol_metadata_mismatches_are_warnings(self):
        row = valid_row(
            symbol="NIFTY23JUN2214000CE",
            strike="24000",
            expiry="2027-12-28",
        )
        report = self.audit_rows([row])
        codes = self.codes(report)
        self.assertIn("CONTRACT_SYMBOL_STRIKE_MISMATCH", codes)
        self.assertIn("CONTRACT_SYMBOL_EXPIRY_MISMATCH", codes)
        self.assertEqual(report["status"], "VALID")
        self.assertEqual(report["counts"]["warnings"], 2)

    def test_symbol_metadata_mismatch_is_reported_once_per_contract_value(self):
        rows = [
            valid_row(symbol="NIFTY23JUN2214000CE", strike="24000", expiry="2027-12-28"),
            valid_row(symbol="NIFTY23JUN2214000CE", strike="24000", expiry="2027-12-28",
                      datetime="2026-07-17 09:22:00"),
        ]
        report = self.audit_rows(rows)
        self.assertEqual(report["counts"]["warnings"], 2)
        self.assertEqual(
            sum(x["code"] == "CONTRACT_SYMBOL_STRIKE_MISMATCH" for x in report["issues"]),
            1,
        )
        self.assertEqual(
            sum(x["code"] == "CONTRACT_SYMBOL_EXPIRY_MISMATCH" for x in report["issues"]),
            1,
        )

    def test_compact_symbol_matching_metadata_has_no_mismatch_warning(self):
        row = valid_row(
            symbol="NIFTY23JUN2214000CE",
            strike="14000",
            expiry="2022-06-23",
        )
        report = self.audit_rows([row])
        self.assertNotIn("CONTRACT_SYMBOL_STRIKE_MISMATCH", self.codes(report))
        self.assertNotIn("CONTRACT_SYMBOL_EXPIRY_MISMATCH", self.codes(report))
    def test_nse_monthly_symbol_matches_year_month_and_strike(self):
        row = valid_row(
            name="ABFRL",
            symbol="ABFRL24JUL250PE",
            strike="250",
            expiry="2024-07-25",
            side="PE",
        )
        report = self.audit_rows([row])
        self.assertNotIn("CONTRACT_SYMBOL_STRIKE_MISMATCH", self.codes(report))
        self.assertNotIn("CONTRACT_SYMBOL_EXPIRY_MISMATCH", self.codes(report))

    def test_nse_monthly_symbol_reports_month_mismatch_without_fake_strike(self):
        row = valid_row(
            name="ABFRL",
            symbol="ABFRL24JUL250PE",
            strike="250",
            expiry="2024-08-25",
            side="PE",
        )
        report = self.audit_rows([row])
        self.assertIn("CONTRACT_SYMBOL_EXPIRY_MISMATCH", self.codes(report))
        self.assertNotIn("CONTRACT_SYMBOL_STRIKE_MISMATCH", self.codes(report))

    def test_nse_weekly_symbol_matches_year_month_day(self):
        row = valid_row(
            symbol="NIFTY25NOV2725000CE",
            strike="25000",
            expiry="2025-11-27",
            side="CE",
        )
        report = self.audit_rows([row])
        self.assertNotIn("CONTRACT_SYMBOL_STRIKE_MISMATCH", self.codes(report))
        self.assertNotIn("CONTRACT_SYMBOL_EXPIRY_MISMATCH", self.codes(report))

    def test_invalid_strike_is_not_reparsed_for_symbol_cross_check(self):
        row = valid_row(symbol="NIFTY23JUN2214000CE", strike="14_000", expiry="2022-06-23")
        report = self.audit_rows([row])
        self.assertIn("INVALID_NUMERIC_VALUE", self.codes(report))
        self.assertNotIn("CONTRACT_SYMBOL_STRIKE_MISMATCH", self.codes(report))

    def test_unknown_symbol_format_is_not_guessed(self):
        row = valid_row(symbol="NIFTY-OPTION-CALL-24000")
        report = self.audit_rows([row])
        self.assertNotIn("CONTRACT_SYMBOL_STRIKE_MISMATCH", self.codes(report))
        self.assertNotIn("CONTRACT_SYMBOL_EXPIRY_MISMATCH", self.codes(report))

    def test_multi_contract_mode_does_not_warn_on_contract_variation(self):
        first = valid_row()
        second = valid_row(symbol="NIFTY_OTHER", strike="25000", datetime="2026-07-17 09:22:00")
        report = self.audit_rows([first, second], single_contract_file=False)
        self.assertNotIn("CONTRACT_FIELD_VARIATION", self.codes(report))

    def test_single_contract_mode_warns_on_contract_variation(self):
        first = valid_row()
        second = valid_row(symbol="NIFTY_OTHER", strike="25000", datetime="2026-07-17 09:22:00")
        report = self.audit_rows([first, second])
        self.assertIn("CONTRACT_FIELD_VARIATION", self.codes(report))

    def test_non_monotonic_timestamp_is_warning(self):
        first = valid_row(datetime="2026-07-17 09:22:00")
        second = valid_row(datetime="2026-07-17 09:21:00")
        report = self.audit_rows([first, second])
        self.assertIn("NON_MONOTONIC_TIMESTAMP", self.codes(report))
        self.assertEqual(report["status"], "VALID")

    def test_timestamp_order_uses_maximum_seen_not_only_previous_row(self):
        rows = [
            valid_row(datetime="2026-07-17 10:00:00"),
            valid_row(datetime="2026-07-17 09:00:00"),
            valid_row(datetime="2026-07-17 09:30:00"),
        ]
        report = self.audit_rows(rows)
        warnings = [x for x in report["issues"] if x["code"] == "NON_MONOTONIC_TIMESTAMP"]
        self.assertEqual(len(warnings), 2)
        self.assertEqual(report["status"], "VALID")

    def test_header_only_file_is_invalid(self):
        report = self.audit_rows([])
        self.assertIn("NO_DATA_ROWS", self.codes(report))

    def test_report_is_json_serializable(self):
        report = self.audit_rows([valid_row()])
        json.dumps(report)
    def test_cli_valid_input_returns_zero_and_prints_json(self):
        path = write_csv([valid_row()])
        try:
            result = subprocess.run(
                [sys.executable, "-m", "src.artifact_auditor", str(path)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "VALID")
        finally:
            path.unlink(missing_ok=True)

    def test_cli_invalid_input_returns_one_and_writes_json_report(self):
        path = write_csv([valid_row(volume="-1")])
        report_path = path.with_suffix(".report.json")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "src.artifact_auditor", str(path), "--json", str(report_path), "--duplicate-store", "sqlite"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "INVALID")
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["status"], "INVALID")
        finally:
            path.unlink(missing_ok=True)
            report_path.unlink(missing_ok=True)


    def test_issue_sample_limit_preserves_exact_counts_and_status(self):
        rows = [
            valid_row(volume="0", oi="0", datetime="2026-07-17 09:21:00"),
            valid_row(volume="-1", oi="0", datetime="2026-07-17 09:22:00"),
        ]
        report = self.audit_rows(rows, max_issues=2)

        self.assertEqual(len(report["issues"]), 2)
        self.assertTrue(report["issues_truncated"])
        self.assertEqual(report["counts"]["errors"], 1)
        self.assertEqual(report["counts"]["info"], 3)
        self.assertEqual(report["issue_counts_by_code"]["ZERO_VOLUME"], 1)
        self.assertEqual(report["issue_counts_by_code"]["ZERO_OPEN_INTEREST"], 2)
        self.assertEqual(report["status"], "INVALID")

    def test_zero_issue_sample_limit_still_reports_invalid_status(self):
        report = self.audit_rows([valid_row(volume="-1")], max_issues=0)

        self.assertEqual(report["issues"], [])
        self.assertTrue(report["issues_truncated"])
        self.assertEqual(report["counts"]["errors"], 1)
        self.assertEqual(report["status"], "INVALID")

    def test_negative_issue_sample_limit_is_rejected(self):
        with self.assertRaises(ValueError):
            self.audit_rows([valid_row()], max_issues=-1)



if __name__ == "__main__":
    unittest.main()
