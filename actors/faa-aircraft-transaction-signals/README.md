# FAA Aircraft Transaction Signals

Self-sourcing lead signals from the FAA's official releasable aircraft registry. The Actor downloads the FAA database, identifies recent sale/registration activity, scores higher-value aircraft and business registrants, and returns a ranked ready-made list without requiring users to maintain N-number lists, company lists, URLs, or keywords.

## Default behavior

- Looks back 14 days.
- Prioritizes LLCs, corporations, partnerships, and non-citizen corporations.
- Detects FAA `Sale reported`, recent certificate issue dates, and recent registry activity.
- Scores turbine aircraft, multi-engine aircraft, recent manufacture years, and business registrants higher.
- Returns the top 100 signals with a minimum score of 60.

## Output

Each row includes signal score/type/reasons, N-number, owner, registrant type, city/state, make/model, manufacture year, aircraft/engine type, registry activity dates, status, and an FAA source link.

## Source

Official FAA Releasable Aircraft Registry database:
https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/releasable_aircraft_download

The FAA states that this downloadable registry is refreshed daily.

## Suggested monetization

Pay per event using `aircraft-transaction-signal`. Start by testing $20 per 1,000 signals ($0.02/signal), then adjust from actual usage and conversion evidence.
