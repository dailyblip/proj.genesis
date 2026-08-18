import asyncio
import requests
from apify import Actor
from .core import (
    carrier_key,
    detect_changes,
    enrich_signal,
    normalize_row,
    qualifies,
    snapshot_row,
)

MOTUS_API = "https://data.transportation.gov/resource/nakq-58th.json"
STATE_STORE = "fmcsa-carrier-intelligence-state-v1"
STATE_KEY = "deficient-carriers"
SELECT_FIELDS = (
    "docket_number,usdot_number,op_auth_type,op_auth_status,min_cov_amount,"
    "bipd_file,cargo_req,cargo_file,bond_req,bond_file,dba_name,legal_name"
)


def fetch_rows(max_source_rows=25000, page_size=5000):
    rows = []
    offset = 0
    while len(rows) < max_source_rows:
        limit = min(page_size, max_source_rows - len(rows))
        params = {
            "$select": SELECT_FIELDS,
            "$where": "min_cov_amount > 0 AND (bipd_file IS NULL OR bipd_file < min_cov_amount)",
            "$limit": str(limit),
            "$offset": str(offset),
            "$order": "docket_number ASC, usdot_number ASC",
        }
        r = requests.get(
            MOTUS_API,
            params=params,
            timeout=90,
            headers={"User-Agent": "FMCSA-Carrier-Intelligence/1.0 public-data-client"},
        )
        r.raise_for_status()
        batch = r.json()
        rows.extend(batch)
        if len(batch) < limit:
            break
        offset += len(batch)
    return rows


async def main():
    async with Actor:
        inp = await Actor.get_input() or {}
        max_results = max(1, min(int(inp.get("maxResults", 250)), 2000))
        min_score = max(0, min(int(inp.get("minScore", 50)), 100))
        min_gap = max(1, int(inp.get("minCoverageGap", 1)))
        include_inactive = bool(inp.get("includeInactive", False))
        changes_only = bool(inp.get("changesOnly", True))
        max_source_rows = max(1000, min(int(inp.get("maxSourceRows", 25000)), 100000))

        raw_rows = fetch_rows(max_source_rows=max_source_rows)
        state_store = await Actor.open_key_value_store(name=STATE_STORE)
        previous_state = await state_store.get_value(STATE_KEY) or {}
        current_state = {}
        signals = []

        for raw in raw_rows:
            row = normalize_row(raw)
            status = (row.get("authorityStatus") or "").strip().lower()
            if not include_inactive and status in {"inactive", "withdrawn"}:
                continue
            if not qualifies(row, min_gap=min_gap):
                continue

            key = carrier_key(row)
            previous = previous_state.get(key)
            current_state[key] = snapshot_row(row)
            triggers = detect_changes(row, previous)

            if changes_only:
                if not triggers:
                    continue
                selected_triggers = triggers
            else:
                selected_triggers = triggers or ["insurance-coverage-gap"]

            for trigger in selected_triggers:
                signal = enrich_signal(row, trigger, previous)
                if signal["signalScore"] < min_score:
                    continue
                signal["carrierKey"] = key
                signal["source"] = "FMCSA Motus Carrier"
                signal["sourceUrl"] = "https://data.transportation.gov/d/nakq-58th"
                signals.append(signal)

        # Persist only after a successful source fetch and transformation.
        await state_store.set_value(STATE_KEY, current_state)

        trigger_priority = {
            "new-insurance-gap": 0,
            "coverage-gap-widened": 1,
            "authority-status-changed": 2,
            "insurance-filing-changed": 3,
            "cargo-filing-changed": 4,
            "bond-filing-changed": 5,
            "coverage-gap-narrowed": 6,
            "insurance-coverage-gap": 7,
        }
        signals.sort(
            key=lambda x: (
                trigger_priority.get(x["trigger"], 99),
                -x["signalScore"],
                -x["coverageGap"],
                x.get("legalName") or "",
            )
        )

        emitted = 0
        for signal in signals[:max_results]:
            charge_result = await Actor.push_data(
                signal,
                charged_event_name="insurance-gap-signal",
            )
            emitted += 1
            if getattr(charge_result, "event_charge_limit_reached", False):
                break

        Actor.log.info(
            f"Scanned {len(raw_rows)} deficient FMCSA records; emitted {emitted} intelligence signals; "
            f"state contains {len(current_state)} carriers."
        )


if __name__ == "__main__":
    asyncio.run(main())
