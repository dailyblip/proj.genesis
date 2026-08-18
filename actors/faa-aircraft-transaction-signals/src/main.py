import asyncio
import csv
import io
import zipfile
from datetime import date

import requests
from apify import Actor

from .core import clean_row, is_business_registrant, normalize_signal, pick, score_signal

FAA_ZIP = "https://registry.faa.gov/database/ReleasableAircraft.zip"


def find_member(zf: zipfile.ZipFile, contains: str):
    contains = contains.upper()
    for name in zf.namelist():
        base = name.rsplit("/", 1)[-1].upper()
        if contains in base and base.endswith((".TXT", ".CSV")):
            return name
    return None


def iter_csv(zf: zipfile.ZipFile, member: str):
    with zf.open(member) as raw:
        text = io.TextIOWrapper(raw, encoding="latin-1", errors="replace", newline="")
        reader = csv.DictReader(text, skipinitialspace=True)
        for row in reader:
            yield clean_row(row)


def aircraft_reference_map(zf: zipfile.ZipFile):
    member = find_member(zf, "ACFTREF")
    if not member:
        return {}
    refs = {}
    for row in iter_csv(zf, member):
        code = str(pick(row, "CODE", "MFR MDL CODE", "MFR_MDL_CODE")).strip()
        if not code:
            continue
        refs[code] = {
            "make": pick(row, "MFR", "MANUFACTURER") or None,
            "model": pick(row, "MODEL") or None,
        }
    return refs


async def main():
    async with Actor:
        inp = await Actor.get_input() or {}
        lookback = max(1, min(int(inp.get("lookbackDays", 14)), 90))
        min_score = max(0, min(int(inp.get("minScore", 60)), 100))
        max_results = max(1, min(int(inp.get("maxResults", 100)), 2000))
        business_only = bool(inp.get("businessOwnersOnly", True))

        Actor.log.info("Downloading the FAA releasable aircraft registry...")
        response = requests.get(
            FAA_ZIP,
            timeout=180,
            headers={"User-Agent": "FAA-Aircraft-Transaction-Signals/0.1 public-data-client"},
        )
        response.raise_for_status()

        zf = zipfile.ZipFile(io.BytesIO(response.content))
        master = find_member(zf, "MASTER")
        if not master:
            raise RuntimeError("FAA registry ZIP did not contain a MASTER file")

        refs = aircraft_reference_map(zf)
        today = date.today()
        signals = []

        for row in iter_csv(zf, master):
            if business_only and not is_business_registrant(row):
                continue
            scored = score_signal(row, today=today, lookback_days=lookback)
            if not scored:
                continue
            score, signal_type, reasons = scored
            if score < min_score:
                continue
            signals.append(normalize_signal(row, refs, score, signal_type, reasons))

        signals.sort(
            key=lambda x: (
                -x["signalScore"],
                x.get("certificateIssueDate") or "",
                x.get("lastActivityDate") or "",
                x.get("nNumber") or "",
            ),
            reverse=False,
        )

        emitted = 0
        for item in signals[:max_results]:
            await Actor.push_data(item)
            try:
                await Actor.charge(event_name="aircraft-transaction-signal", count=1)
            except Exception:
                pass
            emitted += 1

        Actor.log.info(f"Emitted {emitted} FAA aircraft transaction signals.")


if __name__ == "__main__":
    asyncio.run(main())
