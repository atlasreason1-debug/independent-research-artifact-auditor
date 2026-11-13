# Competitive Forensics — Market Data Quality & Research Artifact Validation

**Research date:** 2026-11-13  
**Status:** Desk research; not yet customer-validated  
**Product under review:** Independent Research Artifact Auditor v0.3

## Executive finding

The category is not empty. We found one close open-source competitor focused on equity daily bars, two meaningful adjacent options-data vendors with their own verification controls, generic data-quality frameworks, and internal-build teams at systematic investment firms.

The most defensible initial wedge is not generic market-data validation. It is independent, options-aware validation of customer-supplied research artifacts, especially where contracts, expiries, quotes, open interest, multi-leg activity and cross-vendor consistency matter.

That wedge is only a hypothesis. The current validator is not yet feature-complete for it.

## 1. Competitor map

| Competitor | Category | Evidence-backed capabilities | Gap / distinction |
|---|---|---|---|
| [Market Data Sanity Checker](https://github.com/pacocartones/market-data-sanity-checker) | Closest direct open-source competitor | MIT-licensed Node CLI/SDK; 38 rules (30 single-source, 8 compare); daily OHLCV, dividends, splits, fundamentals and metadata; Yahoo and Alpha Vantage connectors; provider comparison; score; CI gate; history; HTML report; GitHub Action | README explicitly excludes options, futures, intraday and tick data. It is broader and more polished for daily equities than our current tool. |
| [HistoricalData.net](https://historicaldata.net/) | Options/stock data vendor with QA | CSV archives; free stock/options samples; 34-column EOD options schema; downloadable verifier; documented methodology; reconciliation against external Cboe references | Sells data, not a provider-neutral auditor for arbitrary customer research files. Checks are embedded in its own delivery/verification workflow. |
| [ORATS](https://orats.com/) | Options data and research platform | EOD options history since 2007, intraday data since 2020, API, Greeks/IV, option scanning, backtesting and its own verification utility (orats-verify) | Primarily sells and validates its own data and analytics; not positioned as a neutral cross-vendor artifact auditor. |
| [Great Expectations](https://greatexpectations.io/), [Pandera](https://pandera.readthedocs.io/), [Soda](https://www.soda.io/) and Deequ | Generic data-quality frameworks | Schema, null, range, uniqueness and custom assertions; flexible integration into Python/data pipelines | Financial semantics (option contract identity, expiry/settlement, quote/trade activity, Greeks/IV) must be designed and maintained by the user. |
| Internal market-data teams | Build-versus-buy substitute | Quant firms hire specialists to validate, reconcile, normalize and maintain research-grade market datasets | Internal teams may prefer bespoke tooling and have high security/procurement barriers. |

## 2. Detailed direct competitor: Market Data Sanity Checker

Public repository evidence reviewed 2026-11-13:
- Public MIT project, npm package version 1.7.0.
- Repository page showed 4 stars, 7 forks and 167 commits at time of review.
- README lists 38 rules, including corporate actions, currency scaling, stale prices, missing sessions, duplicate timestamps, provider comparisons and tail truncation.
- Product surfaces include CLI, TypeScript SDK, Yahoo/Alpha Vantage connectors, CI gating, history and standalone HTML reports.
- Its README says options, futures, intraday and tick-level streams are out of scope.

Important adoption evidence:
- In [issue #35](https://github.com/pacocartones/market-data-sanity-checker/issues/35), a user asked whether anyone used the product and whether users value the rules or ongoing maintenance.
- The maintainer answered that adoption was early and npm install numbers were not available at that point; the maintainer explicitly avoided guessing.
- This is evidence that even a technically sophisticated open-source project had not publicly demonstrated adoption at that checkpoint. It is not proof nobody uses it, nor proof users will pay.

**Competitive implication:** do not compete on a higher rule count. Compete only if customers demonstrate a costly options-specific gap that MDSC and vendor-specific verification do not solve.

## 3. Adjacent options-data vendors and quality controls

### HistoricalData.net
- Its free options sample contains 127 daily files, 34 columns, and a published example session with 34,898 contract rows.
- Its own sample verifier checks checksums, schema and documented data rules.
- Its published reconciliation page reports 1,016 of 1,021 sample values matching independent references (99.5%) in a dated comparison.
- Its options page reported a rolling Cboe comparison on 2026-11-11: 526,901 of 529,035 counted checks agreed (99.6%) across 97,264 contracts. This is the vendor's published method/result, not an independent audit of the entire market.
- Public list prices at research time: options archive most recent year $160 one-time; full archive $580 one-time; daily updates $68/month. Stock daily archive $199 one-time and daily updates $39/month.

Sources:
- https://historicaldata.net/samples.html
- https://historicaldata.net/options.html
- https://historicaldata.net/data-quality.html
- https://historicaldata.net/terms.html

### ORATS
- Offers EOD options history since 2007 and 1-minute options history since 2020.
- Offers API and analytics products, including Greeks, implied volatility, option scanning and backtesting.
- Its data-quality documentation recommends orats-verify for checking delivered one-minute datasets.
- Pricing pages show distinct data/API tiers; e.g. delayed API at $199/month and live/intraday options API tiers. Historical EOD pricing is separately listed.

Sources:
- https://orats.com/data-api
- https://orats.com/near-eod-data
- https://orats.com/readme-1min.pdf
- https://orats.com/university/historical-data

## 4. Customer-problem evidence (not willingness-to-pay evidence)

Recent role descriptions indicate that market-data quality is an explicit, staffed function inside systematic investment firms:
- [IMC — Data Quality Engineer](https://www.thewallstreetquants.com/jobs/data-quality-engineer-at-imc-8e494f5c-8a62-467a-aca5-3c39e589ddf2): responsibility for integrity, completeness and timeliness of datasets used by researchers/traders; statistical anomaly detection; historical data curation.
- [Trexquant — Senior Data Engineer](https://jobs.workable.com/view/s95Dpb9iNKirLu5GVouBvk/hybrid-senior-data-engineer-%28usa%29-in-stamford-at-trexquant-investment): normalizing and maintaining datasets from hundreds of vendors across equities, options, futures, fixed income and alternatives; data validation and quality control.
- [Qube Research & Technologies — Data Scientist, Market Data](https://www.kadoa.com/quant/job/qrt-data-scientist-market-data-9226b9d7): financial dataset creation, ingestion, validation, delivery and production issue resolution.
- [Bridgewater — Research Associate, Equities Data Engineer](https://haystackapp.io/jobs/28545d05-2ab0-4dc4-8688-32d02a2b53b1): data correctness, lineage, versioning and reproducibility.
- [Verition — Data Sourcing Associate](https://www.wallstreetcareers.com/jobs/641523581-data-sourcing-associate-quant): dataset onboarding, quality, metadata standards and vendor management.

These job descriptions establish that the problem exists and consumes skilled labor in some firms. They do not establish that these firms would buy an external product; many may build internally.

## 5. Positioning implications

### Avoid
- "The first market-data quality tool."
- "No competitors."
- "AI that guarantees clean data."
- Competing head-on with broad daily-equity rule catalogues before our options use case is proven.

### Hypothesis to test
**An independent, reproducible pre-research audit for options datasets from any provider.**

Potentially valuable checks to investigate with users:
- Contract identity, root, expiry, strike, call/put, style and settlement consistency.
- Missing or duplicated contract observations across dates.
- Quote-side validity (bid/ask, crossed markets, stale quotes) with source-aware rules.
- Trade activity semantics: volume, transactions, multi-leg volume and blank OHLC.
- Open-interest timing and reporting conventions.
- Greeks/IV availability and internal consistency, without claiming to recompute or certify vendor models prematurely.
- Vendor-to-vendor parity and coverage differences.
- Reproducible audit manifests: file hash, schema version, ruleset version, exact findings and known limitations.

This is a research direction, not an approved feature roadmap. Each rule requires a sourced failure mode, test fixture and customer confirmation.

## 6. Open questions

1. Do independent quant teams already have effective internal checks, making a separate tool unnecessary?
2. Is the expensive pain bad data, diagnosing bad data, proving dataset provenance, or reproducing old research?
3. Do teams need a local/offline auditor because raw datasets cannot leave their environment?
4. Is the first paying buyer a small fund, independent researcher, data vendor, or research-platform provider?
5. Is an options-only wedge large enough, or do customers require equities/futures/crypto coverage from day one?

## 7. Decision

**No market selection or product lock-in is justified yet.** Keep the current options-capable validator as an engineering hypothesis. Continue competitor monitoring and prioritize customer interviews plus real options data calibration before expanding scope.
