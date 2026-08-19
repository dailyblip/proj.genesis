import csv
import io
import zipfile
from datetime import datetime

import httpx
from apify import Actor
from .core import make_signals, windows

API = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"
BULK_ZIP = "https://files.consumerfinance.gov/ccdb/complaints.csv.zip"


async def fetch_rows_api(client, start, end, size=100000):
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


async def fetch_rows_bulk(client, start, end):
    r = await client.get(BULK_ZIP)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        csv_name = next(name for name in zf.namelist() if name.lower().endswith(".csv"))
        with zf.open(csv_name) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            reader = csv.DictReader(text)
            rows = []
            for rec in reader:
                value = (rec.get("Date received") or "").strip()
                if not value:
                    continue
                parsed = None
                for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
                    try:
                        parsed = datetime.strptime(value, fmt).date()
                        break
                    except ValueError:
                        pass
                if parsed is None or parsed < start or parsed > end:
                    continue
                rows.append({
                    "company": (rec.get("Company") or "").strip(),
                    "product": (rec.get("Product") or "").strip(),
                })
            return rows


async def fetch_rows(client, start, end):
    try:
        return await fetch_rows_api(client, start, end)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in {404, 410, 429, 500, 502, 503, 504}:
            raise
        Actor.log.warning(
            f"CFPB search API returned {exc.response.status_code}; falling back to official CSV ZIP."
        )
        return await fetch_rows_bulk(client, start, end)


async def main():
    async with Actor:
        inp = await Actor.get_input() or {}
        cd = int(inp.get("currentDays", 7))
        bd = int(inp.get("baselineDays", 28))
        minimum = int(inp.get("minCurrentComplaints", 10))
        ratio = float(inp.get("minSpikeRatio", 2.0))
        maximum = int(inp.get("maxSignals", 50))

        cs, ce, bs, be = windows(cd, bd)
        async with httpx.AsyncClient(
            timeout=180,
            follow_redirects=True,
            headers={"User-Agent": "CFPB-Complaint-Spike-Signals/0.1"},
        ) as client:
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
