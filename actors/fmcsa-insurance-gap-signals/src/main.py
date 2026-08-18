import asyncio
import requests
from apify import Actor
from .core import normalize_row, qualifies, score_signal

MOTUS_API = "https://data.transportation.gov/resource/nakq-58th.json"


async def main():
    async with Actor:
        inp = await Actor.get_input() or {}
        max_results = max(1, min(int(inp.get("maxResults", 250)), 2000))
        min_score = max(0, min(int(inp.get("minScore", 50)), 100))
        min_gap = max(1, int(inp.get("minCoverageGap", 1)))

        params = {
            "$select": "docket_number,usdot_number,op_auth_type,op_auth_status,min_cov_amount,bipd_file,cargo_req,cargo_file,bond_req,bond_file,dba_name,legal_name",
            "$where": "min_cov_amount > 0 AND (bipd_file IS NULL OR bipd_file < min_cov_amount)",
            "$limit": str(max(5000, max_results * 20)),
        }

        r = requests.get(
            MOTUS_API,
            params=params,
            timeout=90,
            headers={"User-Agent": "FMCSA-Insurance-Gap-Signals/0.2 public-data-client"},
        )
        r.raise_for_status()
        rows = r.json()

        out = []
        for raw in rows:
            row = normalize_row(raw)
            if not qualifies(row, min_gap=min_gap):
                continue

            row["signalScore"] = score_signal(
                row["bipdRequired"],
                row["bipdOnFile"],
                row["authorityStatus"],
            )
            if row["signalScore"] < min_score:
                continue

            row["trigger"] = "insurance-coverage-gap"
            row["source"] = "FMCSA Motus Carrier"
            row["sourceUrl"] = "https://data.transportation.gov/d/nakq-58th"
            out.append(row)

        out.sort(key=lambda x: (-x["signalScore"], -x["coverageGap"], x.get("legalName") or ""))

        for row in out[:max_results]:
            await Actor.push_data(row)
            try:
                await Actor.charge(event_name="insurance-gap-signal", count=1)
            except Exception:
                pass

        Actor.log.info(f"Emitted {min(len(out), max_results)} insurance-gap signals.")


if __name__ == "__main__":
    asyncio.run(main())
