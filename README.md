# ViajeExpress Payment Intelligence

A runnable payment ETL and interactive analytics prototype. Python's standard library handles ingestion, exact money parsing, SQLite storage, provenance, quarantine, HTML generation and local serving. The dashboard uses vanilla JavaScript and SVG, with no CDN or internet requirement.

## Run in one minute

Requires **Python 3.10+**. No pip installation is needed for the pipeline or dashboard.

From this folder:

```sh
python run.py --serve
```

Open **http://127.0.0.1:8765**. Stop with Ctrl+C. If that port is occupied, use `--port 8766`.

The packaged `data/processed/dashboard.html` also opens directly in a browser, without running Python. It contains the entire dataset and all filters. Offline refresh instructions appear when you click Refresh data.

To regenerate the source data and run without a server:

```sh
python run.py --generate
```

This deliberately does **not** delete an existing database. Loads are idempotent. For a clean first-load demonstration without deleting anything:

```sh
python run.py --output data/review-run --serve
```

Optional notebook: open `ViajeExpress.ipynb` in an existing Jupyter installation, trust it, and Run All. Jupyter/IPython are optional and not required for the main application.

## Five-minute walkthrough

1. Open the dashboard. The first load contains **1,422 unique valid attempts**, from **1,446 deliveries**, across all six PSPs and all six markets. Eighteen invalid rows are quarantined and six duplicate deliveries are skipped.
2. Select **Spain**. Compare PSP4, PSP5 and PSP6 costs in EUR, including fee coverage and mean processing cost. Different payment-method mixes mean this is descriptive, not a causal routing recommendation.
3. Select **Brazil**. PIX, Boleto, transfers/wallets have payment-success rates. Card authorization correctly shows N/A: none of the specified Brazilian PSP contracts supplies cards. N/A is not a zero authorization rate.
4. Reset filters; choose MXN on the trend chart. Switch its breakdown between PSP, market and payment method. All four main filters affect all business metrics, chart, method mix, and exported transactions.
5. Select Mexico / PSP1 and inspect the final weeks for the seeded acceptance drop. The alert compares the last seven days ending at the selected end date with the prior seven days. Small samples are disclosed.
6. Expand **Ingestion quality & source traceability**. Inspect `data/processed/quarantine.json` to see missing amounts, malformed dates and unknown statuses. Open a transaction's source evidence and match the hash to `data/processed/evidence/`.
7. Click **Refresh data** while using the local server. Repeated loads add no duplicate transactions. A repeat of the initial dataset reports 0 inserted, 1,428 duplicates and 18 rejected; quarantine entries are retained per load in SQLite.
8. To demonstrate a new delivery, copy a valid record in `data/raw/psp6.jsonl` to a new line, give it an unused `event_id`, and refresh. Exactly one new transaction appears. Reusing an ID with changed content is quarantined as a conflict rather than silently overwriting evidence.
9. Export the filtered CSV. Review `data/processed/weekly-report.md` for a generated summary of the dataset's latest week.

## Architecture

```text
Six messy source files + manifest
       ↓ provider-specific readers and Adapter contracts
Explicit field, date, status, method and currency normalization
       ↓ exact Decimal → integer minor units
Required-field checks + row validation + duplicate/conflict detection
       ├── quarantine (raw payload + reason + source evidence)
       └── SQLite transactions + immutable source snapshots
                    ↓
       JSON / CSV + dashboard + weekly Markdown report
```

`run.py` orchestrates the pipeline and optional loopback-only HTTP server. `payments/generate.py` creates deterministic data. `payments/adapters.py` contains the six declarative contracts and normalization rules. `payments/pipeline.py` loads data. `payments/metrics.js` implements tested dashboard calculations. `payments/report.py` creates deliverables. `tests/` verifies meaningful failure paths and financial calculations.

### Simulated source contracts

| PSP | Markets | Format | Dates | Example statuses | Money representation |
|---|---|---|---|---|---|
| PSP1 | Mexico, Colombia | JSON array | ISO 8601 with offset | SUCCESS / FAILED | Decimal major units |
| PSP2 | Brazil | CSV | DD/MM/YYYY with offset | PAGO / RECUSADO | Decimal comma |
| PSP3 | Argentina | JSON Lines | Unix seconds | 00 / 05 | Decimal major units |
| PSP4 | Spain, Portugal | XML | DD.MM.YYYY with offset | approved / rejected | Decimal comma |
| PSP5 | All six | CSV | ISO 8601 with offset | COMPLETED / DENIED | Major units; currency names |
| PSP6 | All six | JSON Lines | Unix seconds | 200 / 402 | Integer minor units |

The generator uses 240 unique attempts per PSP, then adds one duplicate delivery to each file. Dates span June 22–September 19, 2026. It includes credit/debit cards, PIX, Boleto, OXXO, bank transfers and wallets; currencies are MXN, BRL, ARS, EUR and COP. Status weights are 80% approved, 15% declined, 3% pending and 2% refunded, with a localized PSP1/Mexico decline spike. Monetary levels are plausible illustrative local-market amounts, not verified exchange-rate conversions. No personal or card data is generated.

### Unified schema and data-quality policy

| Field | Meaning |
|---|---|
| `id` | `PSP:provider_id`; unique within the unified ledger |
| `provider_id`, `psp` | Original source identifier and provider |
| `timestamp` | UTC ISO 8601 timestamp of payment attempt |
| `amount_minor`, `currency` | Nonnegative integer amount; three-letter currency |
| `country`, `method`, `status` | Canonical market, instrument and snapshot status |
| `fee_minor` | Nullable nonnegative fee in transaction currency |
| `quality_notes` | Missing-fee or contract-based currency-resolution warnings |
| `source_file`, `source_row` | Original filename and 1-based record ordinal |
| `source_sha256`, `record_sha256` | Original file hash and normalized content hash |
| `raw_json`, `ingested_at` | Parsed source payload and ingestion time |

All five supported currencies use two decimal places. Decimal parsing prevents float rounding. Too many fractional digits, negatives, non-finite numbers, missing essential fields, unsupported currencies, unknown methods/statuses and timezone-ambiguous dates are rejected. Missing fees remain null. `$` resolves only because these simulated source contracts explicitly guarantee local presentment currency, and the inference is flagged. Production mappings must follow actual PSP documentation; do not apply this assumption generically.

The canonical key counts provider payment attempts. Retried payments routed to another PSP are separate attempts; this prototype has no merchant order identifier with which to deduplicate customers' checkout journeys. Equivalent normalized duplicates are ignored. Conflicting snapshots are quarantined for review; there is no last-write-wins update or event-state machine.

Each source file is retained under its SHA-256 hash, with raw row content and provenance in SQLite. This supports investigation and reproducibility; it does not establish legal authenticity or settlement proof. SQLite is the authoritative queryable store. JSON/CSV/HTML are regenerated read models. A single-process lock serializes server refreshes. Whole-file JSON/XML syntax failures quarantine the file; JSON Lines parsing isolates malformed lines.

## Metric definitions

- **Card authorization:** `(approved + refunded card attempts) / (approved + refunded + declined card attempts)`. Refunded implies an earlier authorization in these simulated snapshot contracts. Pending is excluded; no final card decisions yields N/A.
- **Payment success:** the same ratio across all methods. This avoids labeling asynchronous PIX/Boleto outcomes as card authorizations.
- **Gross TPV:** amounts of approved and refunded attempts. This is approved payment volume, not confirmed bank settlement.
- **Refund volume:** full amounts of refunded attempts, attributed to the original attempt timestamp. Net volume is gross minus refunds. Partial refunds and separate refund-event timing are out of scope.
- **Effective cost:** sum of known fees on successful payments divided by the gross amount of those exact fee-covered payments. Unknown fees are excluded from numerator and denominator; fee coverage is shown.
- **Mean fee per payment:** known successful fees divided by successful payments with known fees. Zero is a known fee. Declined/pending fees are shown separately in all-status known fees.
- **Method share:** count of attempts in the method divided by all selected attempts, including pending/refunded.
- **Currencies:** all monetary totals and comparisons are separated by currency. No invented FX rates or mixed-currency grand totals.
- **Dates:** inclusive UTC day boundaries; trends use Monday-start UTC weeks, including partial boundary weeks.

Example SQLite query (integer amounts are minor units):

```sql
SELECT psp, country,
  100.0 * SUM(status IN ('approved','refunded')) / NULLIF(COUNT(*),0) AS card_auth_pct
FROM transactions
WHERE method IN ('credit_card','debit_card')
  AND status IN ('approved','refunded','declined')
GROUP BY psp, country;
```

## Add another PSP

1. Add an `Adapter` entry in `payments/adapters.py`: canonical-to-source field mapping, exact provider statuses, date format and monetary convention.
2. Add its source file and `{ "psp": "PSP7", "file": "psp7.csv", "format": "csv" }` to the input manifest.
3. For a new file type, extend `read_records`; keep normalization separate. For nested JSON, flatten in a provider-specific reader before normalization.
4. Document timezone, presentment-currency, fee-currency and refund assumptions. Add a representative valid row and failure cases to tests. Run `python run.py`.

## Verification

```sh
python -m unittest discover -s tests -v
node tests/test_metrics.js
```

Node is optional and used only to run the JavaScript metric tests. The application itself needs only Python and a browser. Tests cover all six source formats/contracts, idempotency, conflict quarantine, broken JSONL recovery, exact monetary precision, timezone conversion, invalid statuses/currencies, preserved evidence, rate denominators, currency isolation, refund handling, missing/zero fees and filters.

## Scope and trade-offs

Completed stretch features: exploratory acceptance-drop alerts, generated weekly reporting, and per-source validity/fee-completeness indicators. Timeliness is not scored against today's date for historical synthetic data. Alert thresholds are transparent and sample sizes shown; alerts are not statistically validated and are not sent externally.

The prototype processes batch files; JSON Lines resembles captured webhook payloads, but **no real-time webhook receiver or streaming guarantee is claimed**. Flat input snapshots keep the implementation understandable in the challenge's time budget. It intentionally omits real PSP credentials, authentication, settlement/payout matching, signed webhook verification, event ordering, refund linkage, FX, chargebacks, an automatic scheduler and production deployment. SQLite plus local file exports is suited to this dataset, not multi-tenant distributed ingestion. The server binds only to localhost and is not intended for internet exposure.

For production, introduce immutable provider events with event IDs and effective timestamps, a reviewed lifecycle state machine, merchant order/payment-attempt linkage, payout and fee-ledger reconciliation, incremental checkpoints, schema versioning, access controls, and contract fixtures from each real PSP.
