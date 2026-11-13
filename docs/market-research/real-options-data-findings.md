# Real Options Dataset Smoke Test — Findings

**Run date:** 2026-11-13  
**Source:** HistoricalData.net free options sample  
**Session tested:** 2022-07-01  
**Scope:** One real EOD options session, normalized into the current auditor schema  
**Raw-data policy:** The archive and extracted CSV were held in temporary GitHub Actions storage only. No raw vendor data was committed or uploaded as an artifact.

## 1. Provenance and reproducibility

- Sample archive: https://historicaldata.net/file/options_sample_2022H2.zip
- Vendor sample documentation: https://historicaldata.net/samples.html
- Source CSV: day_by_date/2022-07-01_options.csv
- Source rows: 34,898
- Source file bytes: 6,626,588
- Published and independently verified SHA-256: 00a1c5086256ac6d66fc07f0045e755904fc240dbb29f90f9245ee5142c51ab2
- The workflow downloaded the archive, extracted only the selected daily file and checked the published SHA-256 before processing.

Workflow evidence:
- https://github.com/atlasreason1-debug/independent-research-artifact-auditor/actions/runs/43374974748
- https://github.com/atlasreason1-debug/independent-research-artifact-auditor/actions/runs/43375174239

## 2. Normalization performed

| Vendor field | Auditor field |
|---|---|
| contract | symbol |
| underlying | name |
| quote_date | datetime, normalized to 00:00:00 for daily observation |
| expiration | expiry |
| type: call / put | side: CE / PE |
| strike | strike |
| OHLC | open / high / low / close |
| volume | volume |
| open_interest | oi |
| fixed option dataset label | contract_type = OPT |

The smoke runner also preserves transactions, multileg_volume, active_minutes and last_trade_date as additional columns for diagnostic analysis. The current auditor does not yet apply domain rules to all of those fields.

Important limitation: quote_date is a daily observation date, not an intraday quote timestamp. The midnight value is a normalization key only; it must not be interpreted as the original market timestamp or timezone.

## 3. Audit result

| Metric | All 34,898 rows | Subset with all OHLC fields |
|---|---:|---:|
| Rows audited | 34,898 | 14,433 |
| Rows with complete OHLC | 14,433 | 14,433 |
| Rows without complete OHLC | 20,465 | 0 |
| Error findings | 81,674 | 0 |
| Informational findings | 27,494 | 689 |
| Status | INVALID | VALID |

All-rows findings:
- EMPTY_REQUIRED_VALUE: 81,674
- ZERO_VOLUME: 19,818
- ZERO_OPEN_INTEREST: 7,676

The filtered subset is diagnostic only. It excludes 20,465 rows (58.6% of the session) and cannot be used to claim the entire source dataset is valid.

## 4. Missing-OHLC diagnostics

Rows without all four OHLC values:
- 20,367 rows had all four OHLC fields blank.
- 54 rows had open/high/low blank while close was populated.
- 44 rows had close blank while the other three OHLC fields were populated.

Volume and activity breakdown among the 20,465 rows with incomplete OHLC:
- Volume zero: 19,818 rows.
- Volume positive: 647 rows.
- Transactions positive: 98 rows.
- Transactions zero: 0 rows.
- Transactions blank/other: 20,367 rows.
- Multileg volume positive: 125 rows.
- Multileg volume zero: 27 rows.
- Multileg volume blank/other: 20,313 rows.

Among rows with positive volume and incomplete OHLC:
- 54 had positive transaction counts.
- 593 had blank/other transaction counts.

## 5. Root-cause interpretation

The current validator marks every empty OHLC cell as EMPTY_REQUIRED_VALUE. That assumption is too strict for this options dataset.

The vendor's field documentation states:
- Open/high/low are trade-price fields.
- Close is blank when no same-day trade is recorded.
- Missing values are represented as empty fields, not zeros.
- Volume includes multi-leg trades.
- Transactions is a separate count of trades.
- Multileg volume may be blank when unknown.

Therefore, a blank OHLC field is not automatically proof of corrupt data. In particular, a contract with no trade may legitimately have no OHLC print while still having a valid quote, volume or open-interest record.

However, we must not automatically downgrade every blank:
- 647 incomplete-OHLC rows have positive volume.
- 98 incomplete-OHLC rows have positive transaction counts.
- 54 rows specifically have positive transaction counts while open/high/low are blank.
- The current report does not establish whether these are vendor exceptions, complex-trade semantics, or defects.

**Decision:** do not patch the required-field rule by simply allowing all blank OHLC values. First inspect transaction and multi-leg semantics, compare with the vendor's own verifier, and add explicit conditional tests. The product must distinguish confirmed defects from valid no-trade states and unknown cases.

## 6. Required engineering follow-up

1. Inspect the vendor's own verifier and field-level documentation for conditional OHLC requirements.
2. Profile the 54 rows with positive transactions and missing open/high/low.
3. Profile the 44 rows with missing close but populated open/high/low.
4. Define an explicit options-aware missing-trade policy:
   - confirmed no-trade / unavailable OHLC;
   - trade activity present but expected OHLC missing;
   - insufficient evidence because activity metadata is blank.
5. Add tests for each category before changing production severity.
6. Re-run the complete real-data smoke and Python 3.10–3.12 regression matrix.

## 7. Product lesson

This is the first confirmed real-data calibration issue: **schema validation is not the same as market-semantic validation.**

A generic required-field rule can produce false positives when financial data has conditional field availability. This supports investigating an options-aware audit wedge, but one session from one provider is not enough to validate the market or product demand.
