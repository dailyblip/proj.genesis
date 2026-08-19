import csv
import io
import os
import tempfile
import zipfile
from datetime import datetime

import httpx
from apify import Actor
from .core import make_signals, windows

API = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"
BULK_ZIP = "https://files.consumerfinance.gov/ccdb/complaints.csv.zip"


async def fetch_rows_api(client, start, end, size=100):
    params = {
        "date_received_min": start.isoformat(),
        "date_received_max": end.isoformat(),
        "size": min(size, 100),
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


async def download_bulk_zip(client, path):
    Actor.log.info("Streaming CFPB bulk ZIP to temporary disk storage...")
    async with client.stream("GET", BULK_ZIP) as response:
        response.raise_for_status()
        with open(path, "wb") as out:
            async for chunk in response.aiter_bytes(1024 * 1024):
                out.write(chunk)
    Actor.log.info("CFPB bulk ZIP download complete.")


def parse_date(value):
    value = (value or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


async def fetch_bulk_windows(client, current_start, current_end, baseline_start, baseline_end):
    fd, zip_path = tempfile.mkstemp(prefix="cfpb-", suffix=".zip")
    os.close(fd)
    try:
        await download_bulk_zip(client, zip_path)
        current_rows = []
        baseline_rows = []
        with zipfile.ZipFile(zip_path) as zf:
            csv_name = next(name for name in zf.namelist() if name.lower().endswith(".csv"))
            with zf.open(csv_name) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                reader = csv.DictReader(text)
                for rec in reader:
                    parsed = parse_date(rec.get("Date received"))
                    if parsed is None:
                        continue
                    row = {
                        "company": (rec.get("Company") or "").strip(),
                        "product": (rec.get("Product") or "").strip(),
                    }
                    if current_start <= parsed <= current_end:
                        current_rows.append(row)
                    elif baseline_start <= parsed <= baseline_end:
                        baseline_rows.append(row)
        Actor.log.info(
            f"Bulk fallback loaded {len(current_rows)} current-window and {len(baseline_rows)} baseline complaints."
        )
        return current_rows, baseline_rows
    finally:
        try:
            os.remove(zip_path)
        except FileNotFoundError:
            pass


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
            timeout=300,
            follow_redirects=True,
            headers={"User-Agent": "CFPB-Complaint-Spike-Signals/0.1"},
        ) as client:
            try:
                current_rows = await fetch_rows_api(client, cs, ce)
                baseline_rows = await fetch_rows_api(client, bs, be)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {404, 410, 429, 500, 502, 503, 504}:
                    raise
                Actor.log.warning(
                    f"CFPB search API returned {exc.response.status_code}; using low-memory bulk fallback."
                )
                current_rows, baseline_rows = await fetch_bulk_windows(client, cs, ce, bs, be)

        signals = make_signals(current_rows, baseline_rows, cd, bd, minimum, ratio, maximum)
        Actor.log.info(f"Generated {len(signals)} complaint-spike signals.")
        for signal in signals:
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
