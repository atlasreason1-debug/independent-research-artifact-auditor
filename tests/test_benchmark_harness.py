import tempfile
import unittest
from pathlib import Path

from benchmarks.large_dataset_benchmark import generate_csv, run_isolated


class BenchmarkHarnessTests(unittest.TestCase):
    def test_isolated_audit_worker_can_import_project_package(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "sample.csv"
            generate_csv(csv_path, rows=6, symbols=1, informational=False)

            result = run_isolated("audit", csv_path)

        self.assertEqual(result["mode"], "audit")
        self.assertEqual(result["rows_read"], 6)
        self.assertGreaterEqual(result["issues"], 1)

    def test_isolated_symbol_state_worker_tracks_unique_symbols(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "sample.csv"
            generate_csv(csv_path, rows=12, symbols=3, informational=False)

            result = run_isolated("symbol_state", csv_path)

        self.assertEqual(result["mode"], "symbol_state_only")
        self.assertEqual(result["rows_scanned"], 12)
        self.assertEqual(result["unique_symbols"], 3)

    def test_isolated_bounded_sqlite_audit_worker_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "sample.csv"
            generate_csv(csv_path, rows=1200, symbols=2, informational=True)

            result = run_isolated("audit_bounded_sqlite", csv_path)

        self.assertEqual(result["mode"], "audit_bounded_sqlite")
        self.assertEqual(result["rows_read"], 1200)
        self.assertTrue(result["issues_truncated"])
        self.assertEqual(result["status"], "INVALID")


if __name__ == "__main__":
    unittest.main()
