import asyncio
import re
import time
from datetime import date, timedelta
from xml.etree import ElementTree as ET

import requests
from apify import Actor

BASE = "https://www.sec.gov"
UA = "Genesis SEC Insider Signals research@dailyblip.ai"
HEADERS = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate", "Host": "www.sec.gov"}


def text(node, path, default=""):
    found = node.find(path)
    return (found.text or "").strip() if found is not None and found.text else default


def num(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def index_url(d):
    q = (d.month - 1) // 3 + 1
    return f"{BASE}/Archives/edgar/daily-index/{d.year}/QTR{q}/master.{d:%Y%m%d}.idx"


def recent_form4_paths(days):
    paths = []
    seen = set()
    today = date.today()
    for offset in range(days + 4):
        d = today - timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        try:
            r = requests.get(index_url(d), headers=HEADERS, timeout=45)
            if r.status_code == 404:
                continue
            r.raise_for_status()
        except requests.RequestException:
            continue
        for line in r.text.splitlines():
            parts = line.split("|")
            if len(parts) != 5:
                continue
            cik, company, form, filed, path = [x.strip() for x in parts]
            if form not in {"4", "4/A"} or path in seen:
                continue
            seen.add(path)
            paths.append((filed, cik, company, path))
        if len({p[0] for p in paths}) >= days:
            break
    return paths


def parse_filing(filed, cik, company, path):
    url = f"{BASE}/Archives/{path}"
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    m = re.search(r"(<ownershipDocument[\s\S]*?</ownershipDocument>)", r.text, re.I)
    if not m:
        return []
    root = ET.fromstring(m.group(1))
    owner = root.find("reportingOwner")
    if owner is None:
        return []
    rel = owner.find("reportingOwnerRelationship")
    insider = text(owner, "reportingOwnerId/rptOwnerName")
    title = text(rel, "officerTitle") if rel is not None else ""
    is_director = text(rel, "isDirector") == "1" if rel is not None else False
    is_officer = text(rel, "isOfficer") == "1" if rel is not None else False
    out = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = text(tx, "transactionCoding/transactionCode")
        if code != "P":
            continue
        shares = num(text(tx, "transactionAmounts/transactionShares/value"))
        price = num(text(tx, "transactionAmounts/transactionPricePerShare/value"))
        value = shares * price
        ownership = text(tx, "ownershipNature/directOrIndirectOwnership/value")
        reasons = ["open-market purchase"]
        score = 40
        if is_officer:
            score += 15
            reasons.append("officer purchase")
        if is_director:
            score += 10
            reasons.append("director purchase")
        if value >= 100000:
            score += 10
            reasons.append("$100k+ purchase")
        if value >= 500000:
            score += 10
            reasons.append("$500k+ purchase")
        if value >= 1000000:
            score += 10
            reasons.append("$1m+ purchase")
        if ownership == "D":
            score += 5
            reasons.append("direct ownership")
        out.append({
            "filingDate": filed,
            "issuerName": company,
            "issuerCik": cik,
            "insiderName": insider,
            "insiderTitle": title,
            "isDirector": is_director,
            "isOfficer": is_officer,
            "transactionCode": code,
            "shares": shares,
            "pricePerShare": price,
            "transactionValue": round(value, 2),
            "ownershipType": ownership,
            "signalScore": min(score, 100),
            "reasons": reasons,
            "filingUrl": url,
        })
    return out


async def main():
    async with Actor:
        inp = await Actor.get_input() or {}
        days = max(1, min(int(inp.get("lookbackDays", 3)), 14))
        min_value = max(1, int(inp.get("minTransactionValue", 50000)))
        min_score = max(0, min(int(inp.get("minScore", 55)), 100))
        max_results = max(1, min(int(inp.get("maxResults", 100)), 1000))

        signals = []
        for filed, cik, company, path in recent_form4_paths(days):
            try:
                for item in parse_filing(filed, cik, company, path):
                    if item["transactionValue"] >= min_value and item["signalScore"] >= min_score:
                        signals.append(item)
            except Exception as e:
                Actor.log.warning(f"Skipping {path}: {e}")
            time.sleep(0.12)

        signals.sort(key=lambda x: (-x["signalScore"], -x["transactionValue"], x["filingDate"]))
        for item in signals[:max_results]:
            await Actor.push_data(item)
            try:
                await Actor.charge(event_name="insider-conviction-signal", count=1)
            except Exception:
                pass

        Actor.log.info(f"Emitted {min(len(signals), max_results)} insider conviction signals.")


if __name__ == "__main__":
    asyncio.run(main())
