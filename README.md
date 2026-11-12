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

## Large-dataset reliability checks

The test suite includes generated stress and failure-mode cases:
- 20,200 rows across 200 symbols, including one repeated timestamp per symbol.
- Exact row-count and duplicate-detection assertions at that scale.
- Repeated zero-volume and zero-open-interest findings to expose report growth.
- Malformed CSV input at end-of-file, verifying that rows parsed before the parser error remain counted and the file is marked invalid.

A recent GitHub Actions observation on the 20,200-row case reported:
- Python 3.10: 2.18 seconds, 6.17 MiB tracemalloc peak.
- Python 3.11: 7.42 seconds, 6.14 MiB tracemalloc peak.
- Python 3.12: 4.77 seconds, 5.87 MiB tracemalloc peak.

These are single-run CI observations, not performance guarantees. Tracemalloc measures traced Python allocations, not total process RSS. The current report still emits two informational issue objects for every row where both volume and open interest are zero; report size therefore grows linearly with such rows. Million-row throughput, total process memory, and bounded-report behavior are not yet verified.

## Important limitations

This validator checks internal consistency only. It does not establish that data is authentic, complete against an exchange, correctly adjusted, free from look-ahead bias, or suitable for a profitable strategy. It does not validate backtest execution logic or certify vendor licensing.

Expiry input is expected in the exact format `YYYY-MM-DD` and must be a real calendar date. Timestamp input is currently expected in the exact format `YYYY-MM-DD HH:MM:SS`. The tool does not infer timezone; users must know the source timezone and preserve it in their research metadata.

## Report contract

The CLI prints a JSON object containing `file`, `status`, `mode`, `columns`, `counts`, and `issues`. Each issue has a severity and stable code, with row/column context where applicable.
