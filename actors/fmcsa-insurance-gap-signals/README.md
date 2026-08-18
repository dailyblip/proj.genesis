# FMCSA Carrier Intelligence

Stateful FMCSA lead/intelligence feed for trucking insurance agents and brokers.

The Actor reads public FMCSA/U.S. DOT Motus carrier data, identifies carriers with BI&PD insurance deficiencies, persists a carrier snapshot, and compares later runs against that snapshot so customers can receive newly changed signals instead of the same static list every time.

## Signals
- `new-insurance-gap`
- `coverage-gap-widened`
- `coverage-gap-narrowed`
- `authority-status-changed`
- `insurance-filing-changed`
- `cargo-filing-changed`
- `bond-filing-changed`
- `insurance-coverage-gap` when current-state mode is requested

## Output
Each signal includes carrier identifiers, authority status, required/on-file BI&PD coverage, current coverage gap, prior values when available, trigger, UTC detection timestamp, source link, and a deterministic 0-100 opportunity score.

## Change detection
`changesOnly` defaults to `true`. The first successful run establishes the persistent baseline and treats currently deficient carriers as `new-insurance-gap`. Later runs emit only newly detected changes. Set `changesOnly` to `false` to also return unchanged current insurance-gap records.

State is stored in the named Apify key-value store `fmcsa-carrier-intelligence-state-v1` so it survives individual Actor runs.

## Monetization
The existing Apify PPE event remains `insurance-gap-signal`, avoiding a pricing migration while the product is validated. Every emitted intelligence row is one chargeable signal.

## Data caveat
The source is public FMCSA/U.S. DOT data and its refresh cadence can lag. Signals describe changes observed in the source; they should not be represented as guaranteed same-day changes unless source freshness is independently verified.
