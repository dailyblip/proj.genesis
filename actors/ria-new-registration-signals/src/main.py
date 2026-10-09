import asyncio
from urllib.parse import urljoin

import requests
from apify import Actor
from bs4 import BeautifulSoup

from .core import new_rows, normalize_signal, read_sec_zip

SEC_PAGE = "https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers"
UA = "UltraGenesis-RIA-Signals/0.1 contact: public-data-client"


def discover_registered_archives():
    r = requests.get(SEC_PAGE, timeout=60, headers={"User-Agent": UA})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    found = []
    for a in soup.find_all("a", href=True):
        text = " ".join(a.stripped_strings)
        href = a["href"]
        if "Registered Investment Advisers" not in text:
            continue
        if not href.lower().endswith((".zip", ".xlsx")):
            continue
        found.append((text, urljoin(SEC_PAGE, href)))
    if len(found) < 2:
        raise RuntimeError("Could not discover two current SEC registered-investment-adviser datasets")
    return found[:2]


def download_dataset(url):
    r = requests.get(url, timeout=120, headers={"User-Agent": UA})
    r.raise_for_status()
    if url.lower().endswith(".zip"):
        return read_sec_zip(r.content)
    import io
    import pandas as pd
    return pd.read_excel(io.BytesIO(r.content), dtype=str)


async def main():
    async with Actor:
        inp = await Actor.get_input() or {}
        states = {str(x).strip().upper() for x in inp.get("states", []) if str(x).strip()}
        min_aum = max(0, float(inp.get("minRegulatoryAum", 0) or 0))
        min_score = max(0, min(100, int(inp.get("minScore", 0) or 0)))
        max_results = max(1, min(2000, int(inp.get("maxResults", 250) or 250)))

        archives = discover_registered_archives()
        (latest_label, latest_url), (previous_label, previous_url) = archives[0], archives[1]
        latest = download_dataset(latest_url)
        previous = download_dataset(previous_url)
        fresh = new_rows(latest, previous)

        signals = []
        for _, row in fresh.iterrows():
            signal = normalize_signal(row, latest, latest_label, previous_label)
            if states and (signal.get("state") or "").upper() not in states:
                continue
            if (signal.get("regulatoryAum") or 0) < min_aum:
                continue
            if signal["signalScore"] < min_score:
                continue
            signals.append(signal)

        signals.sort(key=lambda x: (-x["signalScore"], -(x.get("regulatoryAum") or 0), x.get("firmName") or ""))
        emitted = 0
        for signal in signals[:max_results]:
            await Actor.push_data(signal)
            try:
                await Actor.charge(event_name="new-ria-signal", count=1)
            except Exception:
                pass
            emitted += 1

        Actor.log.info(
            f"Compared {latest_label} against {previous_label}; found {len(fresh)} new CRDs; emitted {emitted} signals."
        )


if __name__ == "__main__":
    asyncio.run(main())
