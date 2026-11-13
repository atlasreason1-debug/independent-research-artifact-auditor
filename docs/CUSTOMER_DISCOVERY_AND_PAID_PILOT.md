# Customer Discovery, Competitor Forensics & Paid Pilot Hypothesis

**Research checkpoint:** 2026-11-13  
**Product under test:** Independent Research Artifact Auditor  
**Status:** Desk research only. No customer interviews, dataset commitments, paid-pilot acceptance, contract, or payment have been verified.

## 1. Executive decision

The problem is real, but the market is not empty. There is at least one direct, highly capable adjacent platform (London Data Trading's Nexus), multiple general data-quality frameworks, vendor-specific validation scripts, and data vendors that provide quality controls themselves.

Do not position this as "the first" or "one of very few" market-data validators. Test a narrower wedge:

> A local, source-independent preflight audit for a quant researcher or small systematic team that wants to inspect a vendor CSV artifact before importing it into a research/backtest pipeline, with deterministic findings, row-level evidence, reproducible JSON, and no silent data repair.

The first commercial question is not whether users like the idea. It is whether a buyer has a recurring, costly workflow and will pay to have one real dataset audited.

## 2. Customer pain evidence (not willingness-to-pay evidence)

### Public research

- Bloomberg research reported that historical data coverage, timeliness and quality were the leading research-data challenge for 37% of respondents; normalizing and wrangling multiple providers was selected by 26%. Source: https://www.tradersmagazine.com/featured_articles/coverage-gaps-and-delays-in-data-pose-major-obstacles-for-quants-analysts-and-data-scientists/
- The SigTech Financial Data Impact Report 2023 reports that 52% used third-party service providers for validation/cleaning, 46% used in-house tools, and common problems included duplicates, trading-calendar mismatches and reference-data errors. Source: https://get.sigtech.com/hubfs/Financial_Data_Impact_Report_2023_Final.pdf
- AIMA's alternative-data infrastructure survey reports difficulty backtesting historical data (77% of market leaders; 54% of the rest) and time needed to evaluate data vendors (31% and 33%). This is adjacent evidence, not proof that these buyers need this specific CSV auditor. Source: https://www.aima.org/static/8778b1e4-75c3-44e4-b35dc38e1495001e/Casting-The-Net-v10.pdf

### Public user signals worth interviewing

These are public discussion threads, not qualified leads or paying customers:

1. Quant researcher asking for affordable historical options data for an earnings-volatility thesis; specifically mentions access barriers to WRDS OptionMetrics and LSEG. https://www.reddit.com/r/options/comments/1rcodyu/historical_options_data/
2. Algo-trading user describing historical futures data versus live-feed volume mismatch that changed model behavior. https://www.reddit.com/r/algotrading/comments/1u50cwe/data_blues_looking_for_data_source_advice/
3. User asking whether they should validate futures replay/history before backtesting; responses mention gaps, duplicates, timezones, rollover and bad prints. https://www.reddit.com/r/Trading/comments/1x6wa1a/do_you_guys_actually_check_your_historical_data/
4. User describing historical data source discrepancies between two FX/CFD providers and asking how to reconcile bars. https://www.reddit.com/r/algotrading/comments/1wuts2s/algo_trading_data_source_for_backtesting_and/

The above establish problem language and interview hypotheses only. They do not establish product fit or budget.

## 3. Competitor and substitute map

| Category | Example | What it already does | Implication |
|---|---|---|---|
| Direct / integrated quant platform | London Data Trading — Nexus | Describes 37 market-data check types, raw-data preservation, reversible fixes, quarantine, cross-source/peer checks and dataset promotion. | Strong direct competitor for firms wanting an integrated research-to-execution stack. Do not claim this category is empty. |
| Data-vendor validation | HistoricalData.net `verify.py` and `reconcile.py` | File checksums, structure/date checks, documented rules and selected external reconciliation. | Vendor self-validation already exists; independent cross-vendor checks and pre-purchase evaluation may still be useful. |
| Market-data provider quality practices | Databento | Documents data cleaning, internal consistency checks, provenance, sequence/channel identifiers, dataset conditions and revisions. | Buyers may expect vendors to solve some quality problems; differentiate from selling data itself. |
| General data-quality frameworks | Great Expectations Core, Soda and other observability products | Configurable schema/data assertions and pipeline monitoring. | Flexible substitutes, but users must encode market-specific semantics and integrate/operate them. |
| Lightweight market-data checker | QuantPlace checker mentioned in a public Reddit thread | Claims CSV/ZIP checks for missing values, duplicates, continuity, OHLC, outliers and types. | Low-end/free alternatives exist; verify independently before treating claims as proven. |

Sources:
- Nexus: https://www.londondata.net/nexus/case-study.html
- HistoricalData.net validation methodology: https://historicaldata.net/methodology.html
- Databento data-cleaning article: https://www.databento.tech/blog/data-cleaning
- Great Expectations / Soda comparison: https://learn.soda.io/compare/great-expectations
- QuantPlace mention: https://www.reddit.com/r/mltraders/comments/1t39o4q/why_most_historical_crypto_data_you_find_online/

### Initial differentiation hypothesis

Potential differentiators to test—not yet proven:
- Runs locally against a customer's existing CSV artifact; no warehouse migration or platform adoption.
- Source-independent report that can be attached to a research commit or vendor evaluation.
- Market-specific semantics (contract identity, expiries, sessions, option activity, OHLCV) rather than generic null/duplicate checks.
- Explicitly separates deterministic errors, warnings, informational conditions and unverified claims.
- Preserves original files and never silently repairs data.

## 4. First buyer profile and prospecting order

### Priority A — small systematic / quantitative research teams
**Buyer:** Head of Quant Research, Quant Developer, Research Engineer or Data Engineer.  
**Trigger:** Onboarding a new vendor, importing a historical archive, unexplained backtest/live mismatch, or a new options/futures dataset.  
**Why first:** Pain has a business cost and a team may have budget. Sales cycle may still be longer than an individual researcher.

### Priority B — independent options researchers and advanced practitioners
**Buyer:** Researcher maintaining their own options archive or backtest pipeline.  
**Trigger:** Large chain files, missing/illiquid contract observations, IV/Greek consistency, or affordability/access issues.  
**Why first:** Easy to reach in public quant communities and likely to provide real artifacts; budget may be low.

### Priority C — quant-data engineering consultants and small research software vendors
**Buyer:** Consultant or vendor repeatedly onboarding client datasets.  
**Trigger:** Repeated one-off parsing, validation and reconciliation work.  
**Why first:** Potential repeat use or referral channel; requires proof the tool saves billable engineering time.

### Specific public discovery leads (not contacted)

| Public handle | Publicly stated signal | Why interview | Qualification caveat |
|---|---|---|---|
| `Exarctus` in r/quant | Asked how to quantify options-data errors (e.g. American-style constraints, bid above ask) and whether contracts are consistently present through time; also described institutional data prices as too high for an individual researcher. | Strongest first interview candidate for independent options-data QA and report usefulness. | Thread is about a year old. No evidence they want this product or have budget for it. https://www.reddit.com/r/quant/comments/1pis41w/historical_options_data_at_openclose/ |
| `nuclearmeltdown2015` in r/algotrading | Described a historical-vs-paper-feed volume mismatch that materially changed volume-based features; discussed paying for a short-term data option to test a workflow and a price ceiling for a full provider subscription. | Strongest recent workflow interview candidate; can test whether an audit would have shortened diagnosis. | Their follow-up suggests paper-feed subsampling, not necessarily bad historical data. They paid for data access/testing, not for an auditor. https://www.reddit.com/r/algotrading/comments/1u50cwe/data_blues_looking_for_data_source_advice/ |
| `EliHusky` in r/algotrading | Asked about subtle data corruption and described timestamp drift, duplicate IDs, sequence gaps and timezone-naive bars. | Useful technical interview for edge cases and existing workarounds. | Public discussion does not establish purchasing authority or active need. https://www.reddit.com/r/algotrading/comments/1rzm36t/what_are_some_sneaky_types_of_data_corruption_to/ |

These are public research leads, not confirmed prospects. Do not infer consent to contact or share data from a public post.

### Candidate discovery channels (not contacted)
- r/quant and r/options: options research/data-access conversations.
- r/algotrading and r/Trading: historical/live feed discrepancies and pre-backtest data QA.
- QuantConnect / LEAN and other backtesting communities: developers integrating external data.
- Small systematic funds, proprietary trading groups and quantitative research consultancies: targeted role-based outreach, not mass mailing.

Do not scrape personal contact details or send unsolicited bulk messages. Ask for a voluntary conversation and a redacted sample first.

## 5. Paid pilot offer to test

### Research Data Intake Audit — fixed-scope pilot

**Price hypotheses to test:** USD 99 one-time for an independent researcher (one CSV, up to 250,000 rows, automated report); USD 250 one-time for a small team (one dataset, up to 1,000,000 rows, report plus 30-minute review). These are test prices, not established market prices. Start with the lower-scope offer for an individual prospect; do not discount further before asking what budget they control.

**Deliverables**
1. Input manifest: filename, size, row count and cryptographic hash.
2. Deterministic checks for supported schema, required fields, numeric validity, OHLC consistency, duplicate keys and timestamp ordering.
3. Severity-separated findings with row/field examples and exact counts.
4. JSON report plus a short human-readable findings summary.
5. A 30-minute results review.

**Boundaries**
- No trade signals, profitability claims, strategy review or certification of exchange completeness.
- No silent correction or deletion of source rows.
- Customer must confirm it has the right to share the sample.
- Do not accept confidential/proprietary data until retention, access, transfer and deletion controls are documented and agreed.
- Unsupported formats and semantics are reported as unsupported, not guessed.

**Payment test:** Ask the buyer to pay the fixed pilot fee before doing the full audit. A positive reaction, free-data offer, verbal praise or request for a demo is not willingness to pay. Count only a paid invoice/deposit or signed purchase order as strong evidence.

### Interview questions

1. Tell me about the last time a dataset problem changed or delayed your research.
2. What data source and file format were involved?
3. How did you detect the issue? How long did diagnosis and repair take?
4. What was the consequence: wasted researcher time, delayed launch, incorrect backtest, or vendor escalation?
5. How often does this happen?
6. What checks do you already run, and what do they miss?
7. Would you share a redacted sample to compare your current process with an independent report?
8. If the report finds actionable issues, would you approve a USD 99 fixed-scope audit (individual) or USD 250 (team)? Who controls that budget?
9. What would have to be true for this to be worth paying for again?

Do not lead with the product pitch. Establish the workflow, cost and existing workaround first.

## 6. Outreach message for voluntary discovery

Subject: Quick question about market-data QA before backtesting

Hi — I'm researching how quantitative researchers validate external market-data files before using them in backtests.

I'm building a small, local-first auditor for CSV market-data artifacts. It checks structural and market-specific consistency and produces a reproducible report; it does not generate trading signals or modify source data.

I'm looking for a few researchers who have recently onboarded or reconciled historical stock/options/futures data. Would you be open to a 20-minute conversation about your current workflow? If there is a fit, I can propose a fixed-scope paid audit of one redacted sample. No commitment to share data.

I'd especially value hearing what checks you already trust and where they fail.

## 7. Latest technical verification

**Verified code commit:** `8de604431800c7a7ec068875d3e51f1105442293`  
**Evidence ledger:** refreshed on the current PR head.  
**PR #1:** open and unmerged. The code commit is unchanged by subsequent documentation-only commits. The latest CI runs below were triggered against the latest PR head.

### Automated tests
- GitHub Actions run 43379513188: **54 tests passed** on Python 3.10, 3.11 and 3.12.
- No live-trading or strategy-profitability behavior is included.

### Real market-data smoke tests
- HistoricalData.net sample, 2022-07-01: 34,898 option rows; 14,433 rows with complete OHLC; 20,465 with incomplete OHLC; 691 activity-related warnings; **0 errors**. The provider's verifier passed all 127 files in its published sample archive. This confirms the auditor can preserve and report source-specific OHLC availability; it does not certify every provider observation as economically correct.
- Official NSE F&O UDiFF sample, 2026-11-11: 41,664 option rows; 16,498 positive-volume rows; 25,166 zero-volume rows. The transaction-aware diagnostic found **0 zero-volume rows with positive transaction counts** in this sample. Full-file audit and active-row audit both returned **0 errors**. The source file and normalized diagnostics were temporary; raw vendor data was not retained.
- Latest run 43379513346: both real-data jobs succeeded.

### Large-dataset benchmark
- Latest GitHub Actions run 43379513218: **9/9 scenarios succeeded** on 100K and 1M synthetic rows, with symbol cardinalities of 1, 100, 10K and 100K, plus informational-heavy cases.
- At 1M rows / 100K symbols: bounded in-memory audit peaked at 233.6 MB RSS; bounded SQLite audit peaked at 35.9 MB RSS. Runtime was 18.4s versus 20.6s respectively; both retained exact issue counts and capped the report sample at 1,000 findings.
- At 1M rows / 100 symbols with informational-heavy findings: the unbounded report was 344.74 MB and peaked at 1,352.5 MB RSS; bounded in-memory mode peaked at 205.7 MB; bounded SQLite mode retained exact counts in a 0.16 MB report at 20.9 MB peak RSS.
- These are synthetic, machine-dependent measurements, not production service-level guarantees. SQLite is opt-in and trades runtime for lower peak memory.

## 8. Evidence ledger and decision gates

| Question | Current evidence | Status |
|---|---|---|
| Is data-quality pain real? | Industry surveys and public user discussions | Supported at category level |
| Are there direct competitors? | Nexus and vendor-specific validation/reconciliation | Yes |
| Is there a narrow wedge? | Local preflight artifact audit is plausible | Hypothesis |
| Is the current technical baseline reproducibly tested? | 54 tests across Python 3.10–3.12; both real-data smoke jobs; all 9 benchmark scenarios passed at the verified branch head | Verified for the listed commit and samples; not a production certification |
| Has a real target user agreed to share a dataset? | No verified agreement | Not verified |
| Has anyone agreed to a paid pilot? | No | Not verified |
| Has any payment occurred? | No | No |

**Next gates**
1. Begin customer discovery with at least 5 interviews across Priority A and B; Exarctus remains an uncontacted public lead until the Founder sends the prepared message and receives a reply.
2. Obtain at least 2 redacted sample datasets with explicit permission; do not accept confidential data until handling and deletion controls are agreed.
3. Send the fixed USD 99 / USD 250 pilot hypotheses only to qualified prospects and record accept / reject / counter-offer.
4. Count only a paid invoice/deposit or signed purchase order as strong willingness-to-pay evidence.
5. Do not expand product scope until real customer datasets and buyer workflows reveal a repeated unmet need.
