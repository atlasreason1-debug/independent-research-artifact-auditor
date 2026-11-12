# Independent Research Artifact Auditor

A deterministic first-pass auditor for CSV market-data artifacts used in quantitative research.

## Current scope

The v0.3 validator checks:
- Required schema, duplicate/empty headers, short rows, extra fields, and empty files.
- Required values, numeric parsing, finite numbers, and non-negative market fields.
- OHLC consistency.
- Canonical timestamps, duplicate symbol/timestamp pairs, and non-monotonic time order.
- Option side and contract-type labels.
- Optional single-contract consistency warnings.

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

## Important limitations

This validator checks internal consistency only. It does not establish that data is authentic, complete against an exchange, correctly adjusted, free from look-ahead bias, or suitable for a profitable strategy. It does not validate backtest execution logic or certify vendor licensing.

Timestamp input is currently expected in the exact format `YYYY-MM-DD HH:MM:SS`. The tool does not infer timezone; users must know the source timezone and preserve it in their research metadata.

## Report contract

The CLI prints a JSON object containing `file`, `status`, `mode`, `columns`, `counts`, and `issues`. Each issue has a severity and stable code, with row/column context where applicable.
