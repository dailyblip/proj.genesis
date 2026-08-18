# FMCSA Insurance Gap Signals

Self-sourcing lead feed for trucking insurance agents and brokers.

The Actor reads public FMCSA/U.S. DOT carrier data and emits carriers with a visible gap between required BI&PD liability coverage and coverage on file.

## Output
- carrier name / USDOT
- authority status
- required BI&PD
- BI&PD on file
- coverage gap
- fleet size
- location/contact fields where available
- deterministic 0-100 signal score

## Monetization
Apify PPE event: `insurance-gap-signal`
Suggested test price: $0.10 per qualifying signal.

## Caveat
Source refresh cadence can lag. Do not market every row as a same-day lead unless live data freshness is verified.
