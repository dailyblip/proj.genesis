import httpx
from apify import Actor
from .core import make_signals, windows

API = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"


async def fetch_rows(client, start, end, size=100000):
    params = {
        "date_received_min": start.isoformat(),
        "date_received_max": end.isoformat(),
        "size": size,
        "format": "json",
        "no_aggs": "true",
        "sort": "created_date_desc",
    }
    r = await client.get(API, params=params)
    r.raise_for_status()
    hits = r.json().get("hits", {}).get("hits", [])
    rows = []
    for hit in hits:
        src = hit.get("_source", hit)
        rows.append({"company": src.get("company", ""), "product": src.get("product", "")})
    return rows


async def main():
    async with Actor:
        inp = await Actor.get_input() or {}
        cd = int(inp.get("currentDays", 7))
        bd = int(inp.get("baselineDays", 28))
        minimum = int(inp.get("minCurrentComplaints", 10))
        ratio = float(inp.get("minSpikeRatio", 2.0))
        maximum = int(inp.get("maxSignals", 50))

        cs, ce, bs, be = windows(cd, bd)
        async with httpx.AsyncClient(timeout=90, headers={"User-Agent": "CFPB-Complaint-Spike-Signals/0.1"}) as client:
            current_rows = await fetch_rows(client, cs, ce)
            baseline_rows = await fetch_rows(client, bs, be)

        for signal in make_signals(current_rows, baseline_rows, cd, bd, minimum, ratio, maximum):
            signal.update({
                "windowStart": cs.isoformat(),
                "windowEnd": ce.isoformat(),
                "baselineStart": bs.isoformat(),
                "baselineEnd": be.isoformat(),
                "source": "CFPB Consumer Complaint Database",
            })
            await Actor.push_data(signal)
            try:
                await Actor.charge(event_name="complaint-spike-signal")
            except Exception:
                pass


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
