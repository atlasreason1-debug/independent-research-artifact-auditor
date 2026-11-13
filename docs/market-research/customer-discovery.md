# Customer Discovery — First User & Willingness-to-Pay Evidence

**Research date:** 2026-11-13  
**Status:** Candidate discovery plan; no interviews or paid commitments verified  
**Objective:** Find one real user, one costly data-quality problem, one useful solution and one paid pilot.

## 1. Current evidence status

| Evidence | Status | What it proves |
|---|---|---|
| Quant firms hire market-data quality/data-engineering roles | Observed in public job descriptions | Data correctness, completeness, validation and curation consume skilled labor. |
| Options-data vendors publish verification procedures | Observed | Providers themselves recognize the need to validate files and reconcile data. |
| A direct open-source checker exists | Verified | There is a competing solution and a community interested in financial data-quality rules. |
| A user needs our auditor today | Not verified | No confirmed interview or actual dataset supplied by an external user. |
| Willingness to pay for our auditor | Not verified | No quote acceptance, paid pilot, LOI, PO or payment. |
| First paying customer | Not achieved | Do not claim revenue or product-market fit. |

**Important:** Prices paid for market-data archives or APIs are evidence of spending on data, not evidence of willingness to pay for an independent auditor.

## 2. Initial customer hypotheses

### ICP A — Independent options researcher / small systematic team
- Uses EOD or intraday options CSV files from one or more providers.
- Builds research and backtests in Python.
- Has no dedicated market-data QA engineer.
- Currently relies on scripts, manual spot checks or provider-specific verification.
- Likely user: quant researcher / strategy developer.
- Likely buyer: founder, research lead or CTO.

**Why test first:** Shorter decision path than large institutions; can share a bounded sample and decide on a small pilot faster. This is a hypothesis, not validated.

### ICP B — Boutique prop firm / systematic asset manager
- Ingests options, equities or other market datasets from several vendors.
- Needs reproducible research inputs and fewer data incidents.
- Has a data engineer or research-platform owner.
- Likely buyer: Head of Quant Research, Head of Data Engineering or CTO.

**Risk:** Longer sales cycle and stronger internal-build capability.

### ICP C — Market-data vendor / dataset broker
- Needs independent evidence that published files meet documented quality expectations.
- Could use an auditor for pre-release QA, customer support or dataset acceptance.
- Likely buyer: Head of Data Operations, Data Quality Lead or Product Lead.

**Risk:** Existing proprietary verification may already be sufficient; an independent tool may be viewed as competitive or unnecessary.

## 3. Candidate first-user account list

These are target accounts for discovery, not confirmed leads or customers. No personal contact has been approached.

| Candidate | Public signal | Suggested role to contact | Priority |
|---|---|---|---|
| Small independent options research developers using ORATS or HistoricalData.net files | Directly use the artifact type our current validator can process | Founder / Quant Researcher | **First** |
| Boutique options-focused prop/systematic firms | Need options research datasets and pipeline reliability | Quant Lead / Data Engineer | **First** |
| Trexquant Investment | Public role describes multi-vendor datasets across options/futures/equities and validation | Data Engineering Lead / Market Data | Second; enterprise |
| Qube Research & Technologies | Public role describes market-data ingestion, validation and production issue resolution | Market Data Lead | Second; enterprise |
| IMC Trading | Dedicated Data Quality team and historical dataset ownership described in role | Data Quality Engineering Lead | Second; enterprise |
| Bridgewater Associates | Public role emphasizes correctness, lineage, versioning and reproducibility | Equities Data Engineering Lead | Second; enterprise |
| Verition Fund Management | Public role covers data sourcing, onboarding, quality and vendor management | Quant Data Sourcing Lead | Second; enterprise |
| HistoricalData.net / ORATS | Vendors publish verification procedures and data-quality claims | Data Operations / Product | Partner or benchmark conversation, not first buyer assumption |

Public role evidence:
- IMC: https://www.thewallstreetquants.com/jobs/data-quality-engineer-at-imc-8e494f5c-8a62-467a-aca5-3c39e589ddf2
- Trexquant: https://jobs.workable.com/view/s95Dpb9iNKirLu5GVouBvk/hybrid-senior-data-engineer-%28usa%29-in-stamford-at-trexquant-investment
- QRT: https://www.kadoa.com/quant/job/qrt-data-scientist-market-data-9226b9d7
- Bridgewater: https://haystackapp.io/jobs/28545d05-2ab0-4dc4-8688-32d02a2b53b1
- Verition: https://www.wallstreetcareers.com/jobs/641523581-data-sourcing-associate-quant

## 4. Discovery questions

Do not pitch first. Ask about the user's last real incident and current workflow.

1. Walk me through the last time a market-data file caused a research or backtest problem.
2. Which dataset/provider, asset class, format and approximate size were involved?
3. How did you discover the issue? What checks ran before the research started?
4. What was wrong: missing contracts, duplicate timestamps, incorrect expiry, bad quotes, stale values, corporate actions, symbol mapping, or something else?
5. How many engineer/researcher hours did diagnosis and correction consume?
6. What downstream work had to be repeated or discarded?
7. Which checks do you maintain yourself? Can you show a redacted or synthetic version of the report?
8. What does your team currently pay for data validation, reconciliation or data engineering?
9. Who owns the budget and who approves a new tool?
10. If we audited one representative file and found a reproducible issue, what would need to be true for you to pay for a bounded pilot?

Ask for a recent file or a sanitized sample only after permission. Never request API keys, credentials, proprietary data without authorization, or unrestricted access.

## 5. What counts as willingness-to-pay evidence

Rank evidence from weak to strong:

1. **Weak:** "Interesting idea", stars, likes, survey interest, or a hypothetical "I would pay".
2. **Useful:** User shares a real sample, explains a costly incident and agrees to review findings.
3. **Stronger:** User requests a defined pilot scope, introduces the budget owner, or asks for a formal quote.
4. **Strong:** User accepts a priced pilot proposal or signs a purchase order / contract.
5. **Conclusive for first revenue:** Payment received and pilot delivered with user-confirmed value.

Do not report levels 1–3 as revenue or product-market fit.

## 6. First pilot hypothesis

Offer a tightly bounded, human-reviewed audit of one options research artifact:
- One provider and one agreed date range.
- One agreed file format and size limit.
- Deterministic checks only; no trade recommendations or profitability claims.
- Findings grouped by severity, with row/field evidence and reproducibility metadata.
- Clear distinction between confirmed defects, warnings, legitimate blanks and unknowns.
- Raw files remain with the customer if local execution is required; no retention or redistribution without explicit agreement.
- Deliver a short report and review call.

Price is intentionally **not set**. First determine the customer's current cost of the problem, procurement path and the value of a verified audit. Then ask for a real paid pilot decision rather than a hypothetical price preference.

## 7. Initial outreach message

**Subject: Quick question about validating options research data**

Hi,

I'm researching how independent quant teams validate historical options datasets before using them in research or backtests.

I'm not trying to sell a trading signal or a data feed. I'm trying to understand how teams catch issues such as missing or duplicated contracts, expiry/strike inconsistencies, quote/trade gaps and provider differences.

Could I ask you about the last time a data-quality issue affected your research workflow? If useful, I can also run a small, bounded audit on a sample you are authorized to share and show exactly what the checks can and cannot establish.

Would you be open to a 15-minute conversation?

Thanks.

## 8. Next discovery sprint

1. Build a list of 20 independent options researchers and boutique systematic teams.
2. Send 10 highly targeted, personalized outreach messages after Founder approval.
3. Secure 5 discovery conversations.
4. Obtain 2 authorized sample datasets.
5. Run 2 manual audits and ask users to rank the findings by operational impact.
6. Present one priced pilot offer to a user who has a recent, costly problem.
7. Continue only if the problem, value and buyer are real.

## 9. Stop / pivot criteria

Revisit the product hypothesis if:
- Most target users say their current checks are sufficient and recent failures are rare.
- No one can identify a costly incident or quantify the time spent.
- Users will share data but will not pay for a result.
- Their main problem is source authenticity or legal provenance, which the current validator cannot establish.
- They require a full enterprise data platform before a narrow audit has value.

**Current conclusion:** the problem is credible, but customer demand and willingness to pay remain unverified. The next milestone is not more features; it is a real user submitting a representative dataset and agreeing to a paid pilot if the audit proves useful.
