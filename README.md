# Independent Research Artifact Auditor

A deterministic first-pass auditor for CSV market-data artifacts used in quantitative research.

## Current scope

The v0.3 validator checks:
- Required schema, duplicate/empty headers, short rows, extra fields, and empty files.
- Required values, strict decimal/scientific numeric tokens (without binary-float precision loss), finite numbers, and non-negative market fields. Thousands separators and digit underscores are rejected rather than guessed.
- Real calendar-date validation for expiry values in exact `YYYY-MM-DD` format.
- OHLC consistency.
- Canonical timestamps, duplicate symbol/timestamp pairs, and non-monotonic time order.
- Option side and contract-type labels.
- Optional single-contract consistency warnings.
- Recognized compact option symbols in the observed `{name}{DDMMMYY}{strike}{CE|PE}` shape are cross-checked against expiry, strike, and side metadata; mismatches are warnings, not automatic invalidations. Unknown symbol formats are not guessed.

Zero volume and zero open interest are informational, not automatic failures. In particular, zero open interest can mean the provider has not reported it.

## Run

A clearly labeled synthetic example is included at `examples/sample_options.csv`. It is test data only, not a licensed vendor feed or evidence of real market conditions.

Requires Python 3.10+; runtime uses only the Python standard library.

```bash
python -m src.artifact_auditor path/to/data.csv
python -m src.artifact_auditor path/to/data.csv --json report.json
python -m src.artifact_auditor path/to/multi_contract.csv --multi-contract
python -m unittest discover -s tests -v
```

Exit code: `0` when the report status is VALID, `1` when INVALID.

## Large-dataset benchmark (experimental)

A reproducible benchmark harness is available:

```bash
python benchmarks/large_dataset_benchmark.py --rows 100000 --symbols 100
python benchmarks/large_dataset_benchmark.py --rows 1000000 --symbols 10000
python benchmarks/large_dataset_benchmark.py --rows 1000000 --symbols 10000 --informational
```

It generates a synthetic CSV, then runs three isolated processes:
1. The current end-to-end `audit_csv` path, recording elapsed time, peak process RSS, parsed row count, issue count, and serialized JSON report size.
2. A duplicate-key-only baseline using an in-memory Python set.
3. A duplicate-key-only baseline using a temporary SQLite database with a composite primary key.

The duplicate-key comparison is an isolated storage experiment, **not** a production implementation or a claim that SQLite can be substituted without design and correctness work. The informational scenario sets both volume and OI to zero on every row to expose issue-report growth.

A manual GitHub Actions workflow, **large-dataset-benchmark**, can run 100,000 or 1,000,000 rows with 1, 100, or 10,000 symbols. It uploads the JSON measurements as a workflow artifact. Run it on the `feat/validator-v0-3` branch. Linux peak RSS is reported using `resource.getrusage`; it includes Python process memory, unlike `tracemalloc` which tracks Python allocations only.

**No 100K or 1M benchmark result is currently certified.** The harness must be run and its artifact inspected before making scalability claims or selecting a memory-control patch. Benchmark values are machine- and workload-dependent, not service-level guarantees.

## Important limitations

This validator checks internal consistency only. It does not establish that data is authentic, complete against an exchange, correctly adjusted, free from look-ahead bias, or suitable for a profitable strategy. It does not validate backtest execution logic or certify vendor licensing.

Expiry input is expected in the exact format `YYYY-MM-DD` and must be a real calendar date. Timestamp input is currently expected in the exact format `YYYY-MM-DD HH:MM:SS`. The tool does not infer timezone; users must know the source timezone and preserve it in their research metadata.

## Report contract

The CLI prints a JSON object containing `file`, `status`, `mode`, `columns`, `counts`, and `issues`. Each issue has a severity and stable code, with row/column context where applicable.
