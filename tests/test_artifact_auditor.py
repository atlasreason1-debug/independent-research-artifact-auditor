import csv
import json
import tempfile
import unittest
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
        row[REQUIRED_COLUMNS.index("close")] = ""
        report = self.audit_rows([row])
        matching = [x for x in report["issues"] if x.get("column") == "close"]
        self.assertEqual([x["code"] for x in matching], ["EMPTY_REQUIRED_VALUE"])

    def test_nan_and_infinity_are_non_finite(self):
        row = valid_row(open="NaN", close="inf")
        report = self.audit_rows([row])
        self.assertEqual(sum(x["code"] == "NON_FINITE_VALUE" for x in report["issues"]), 2)

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
        report = self.audit_rows([valid_row(open="11", high="10", low="12", close="11")])
        self.assertIn("INVALID_OHLC_HIGH", self.codes(report))
        self.assertIn("INVALID_OHLC_LOW", self.codes(report))

    def test_duplicate_timestamp_same_symbol_is_invalid(self):
        report = self.audit_rows([valid_row(), valid_row()])
        self.assertIn("DUPLICATE_CONTRACT_TIMESTAMP", self.codes(report))

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


if __name__ == "__main__":
    unittest.main()
