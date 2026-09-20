# Validation record

Verified on September 20, 2026, using Python 3.14.3 and Node 24.14.1.

- Six Python unit tests passed: complete multi-source load and idempotency, conflict quarantine, exact amounts, timezone/status/currency validation, malformed JSONL isolation, and queryable provenance.
- JavaScript metric assertions passed for card/payment denominators, refunds, currency separation, matched fee coverage, zero fees, empty populations and combined filters.
- Fresh load: 1,446 deliveries → 1,422 unique valid transactions; six duplicates; 18 quarantined rows. Six PSPs, six countries, five currencies.
- Browser opened successfully with 1,422 attempts, 83.5% card authorization and 84.4% all-method success.
- Brazil filter: 315 attempts, 85.1% payment success, card authorization N/A, and only BRL monetary totals.
- Combined filter Brazil / PSP2 / PIX / September 1–19: 27 attempts, 26 final decisions, 80.8% payment success, one pending payment, and 61,213.86 BRL gross TPV.
- Browser refresh completed with zero new records and preserved all four filter selections. Reset restored all 1,422 attempts.
- Dashboard visually inspected in the app browser. The notebook's code cells were syntax-checked; execution of its optional Jupyter iframe depends on the reviewer's notebook frontend and trust settings.

These checks validate the demonstration and its stated contracts, not production readiness or real-provider accounting accuracy.
