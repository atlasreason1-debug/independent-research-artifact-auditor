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


if __name__ == "__main__":
    unittest.main()
