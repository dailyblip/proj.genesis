import asyncio
import csv
import io
import requests
from apify import Actor
from .core import normalize_row, qualifies, score_signal

MOTUS_URL = "https://data.transportation.gov/api/views/az4n-8mr2/rows.csv?accessType=DOWNLOAD"


async def main():
    async with Actor:
        inp = await Actor.get_input() or {}
        max_results = max(1, min(int(inp.get("maxResults", 250)), 2000))
        min_score = max(0, min(int(inp.get("minScore", 50)), 100))
        min_gap = max(1, int(inp.get("minCoverageGap", 1)))
        states = {str(s).upper() for s in inp.get("states", []) if str(s).strip()}

        r = requests.get(
            MOTUS_URL,
            timeout=90,
            headers={"User-Agent": "FMCSA-Insurance-Gap-Signals/0.1 public-data-client"},
        )
        r.raise_for_status()

        reader = csv.DictReader(io.StringIO(r.text))
        out = []

        for raw in reader:
            row = normalize_row(raw)

            if states and (row.get("state") or "").upper() not in states:
                continue
            if not qualifies(row, min_gap=min_gap):
                continue

            row["signalScore"] = score_signal(
                row["bipdRequired"],
                row["bipdOnFile"],
                row["powerUnits"],
                row["authorityStatus"],
            )
            if row["signalScore"] < min_score:
                continue

            row["trigger"] = "insurance-coverage-gap"
            row["source"] = "FMCSA / U.S. DOT public carrier data"
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
