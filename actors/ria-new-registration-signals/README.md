# New RIA Registration Signals

A low-cost lead/intelligence feed that compares the two newest SEC monthly Registered Investment Adviser datasets and emits firms whose CRD number appears in the newest file but not the prior month.

## Buyers
Asset managers, custodians, fintech vendors, compliance/cybersecurity firms, recruiters, and other vendors selling into RIAs.

## Output
- firm name / CRD / SEC number
- filing date
- city/state
- public phone and website where present in the SEC report
- regulatory AUM and employee count where present
- deterministic 0-100 signal score
- exact SEC source metadata

## Economics
The source files are public SEC monthly downloads. The actor downloads only the two newest registered-adviser files, so source and compute costs are low. Suggested initial Apify PPE event: `new-ria-signal`; price should be validated against marketplace conversion rather than assumed.

## Caveat
A new CRD in the monthly SEC dataset is an observed new appearance in the SEC-registered-adviser report, not a guarantee that the business itself was newly formed that month. Do not market the signal as company formation data.
