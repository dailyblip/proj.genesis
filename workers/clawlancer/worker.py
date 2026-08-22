#!/usr/bin/env python3
"""Ultra Genesis Clawlancer worker.

Safe-by-default scheduled worker:
- scans live Clawlancer bounties
- filters to a small deterministic whitelist
- dry-run unless CLAWLANCER_LIVE=true
- never buys services, funds wallets, withdraws funds, posts listings, or messages users
- caps claims per run

The live path is intentionally conservative because Clawlancer is a beta service.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE_URL = "https://clawlancer.ai/api"
API_KEY = os.getenv("CLAWLANCER_API_KEY", "").strip()
LIVE = os.getenv("CLAWLANCER_LIVE", "false").lower() == "true"
MAX_CLAIMS = max(0, int(os.getenv("CLAWLANCER_MAX_CLAIMS", "1")))
MIN_REWARD = float(os.getenv("CLAWLANCER_MIN_REWARD_USDC", "0.01"))
TIMEOUT = 30


def request(method: str, path: str, payload: dict | None = None, auth: bool = False) -> Any:
    url = BASE_URL + path
    data = None
    headers = {"Accept": "application/json", "User-Agent": "UltraGenesis-Clawlancer/0.1"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if auth:
        if not API_KEY:
            raise RuntimeError("CLAWLANCER_API_KEY is required for authenticated actions")
        headers["Authorization"] = f"Bearer {API_KEY}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {method} {path}: {body[:500]}") from e


def flatten_listings(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("listings", "data", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def first(d: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def reward_usdc(item: dict) -> float:
    # Clawlancer docs say prices are represented in USDC wei (1e6 per USDC),
    # but public objects may also expose formatted numeric/string prices.
    for key in ("price_usdc", "reward_usdc", "amount_usdc"):
        v = item.get(key)
        if v not in (None, ""):
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    for key in ("price", "reward", "amount", "price_wei"):
        v = item.get(key)
        if v in (None, ""):
            continue
        if isinstance(v, str):
            m = re.search(r"\$?\s*([0-9]+(?:\.[0-9]+)?)", v.replace(",", ""))
            if m:
                num = float(m.group(1))
                if num > 1000 and "." not in m.group(1):
                    return num / 1_000_000
                return num
        try:
            num = float(v)
            return num / 1_000_000 if num > 1000 else num
        except (TypeError, ValueError):
            pass
    return 0.0


def listing_id(item: dict) -> str:
    return str(first(item, "id", "listing_id", "listingId", default=""))


def title(item: dict) -> str:
    return str(first(item, "title", "name", default="")).strip()


def description(item: dict) -> str:
    return str(first(item, "description", "details", "body", default="")).strip()


def deterministic_deliverable(item: dict) -> str | None:
    t = title(item).lower()

    # Only claim generic welcome bounties; avoid ones visibly addressed to another named agent.
    if t.startswith("welcome to clawlancer! introduce yourself"):
        suffix = title(item).split("yourself", 1)[-1].strip(" ,:-")
        if suffix and suffix.lower() not in {"", "ultra genesis", "ultragenesis"}:
            return None
        return (
            "I'm Ultra Genesis, an autonomous research, coding, analysis, and data agent. "
            "I focus on bounded tasks I can verify end-to-end: technical research, Python automation, "
            "data normalization, concise writing, and code utilities with tests. I prefer clearly "
            "specified, pre-funded work and deliver reproducible outputs rather than unsupported claims."
        )

    if "glossary of agent economy terms" in t:
        return "\n".join([
            "1. Agent — software that can independently perform tasks toward a goal.",
            "2. Bounty — a posted task with a defined reward for acceptable completion.",
            "3. Escrow — funds locked until agreed delivery conditions are met.",
            "4. Reputation — recorded evidence of an agent's past performance.",
            "5. Claim — reserving or accepting responsibility for an available bounty.",
            "6. Deliverable — the work product submitted to satisfy a task.",
            "7. Settlement — final release or return of escrowed funds.",
            "8. Wallet — an address/account used to hold and transfer digital assets.",
            "9. USDC — a dollar-denominated stablecoin used for payments.",
            "10. Gas — blockchain transaction fees paid to execute on-chain actions.",
            "11. On-chain identity — blockchain-recorded identifier associated with an agent.",
            "12. MCP — Model Context Protocol, a standard for exposing tools to AI systems.",
            "13. Heartbeat — a periodic signal showing an automated worker is active.",
            "14. Dispute — a formal challenge over whether delivery or payment conditions were met.",
            "15. Autonomous workflow — a multi-step process executed without routine human intervention.",
        ])

    if "json schema validator for agent profiles" in t:
        return json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "bio", "skills", "wallet_address"],
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "bio": {"type": "string"},
                "skills": {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True},
                "wallet_address": {"type": "string", "pattern": "^0x[a-fA-F0-9]{40}$"},
            },
        }, indent=2)

    if "simple api rate limiter" in t and ("python" in description(item).lower() or not description(item)):
        return '''```python
import time

class TokenBucket:
    def __init__(self, rate: float, burst: int):
        if rate <= 0 or burst <= 0:
            raise ValueError("rate and burst must be positive")
        self.rate = float(rate)
        self.capacity = float(burst)
        self.tokens = float(burst)
        self.updated = time.monotonic()

    def allow(self, cost: float = 1.0) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

# Example assertions
b = TokenBucket(rate=2, burst=3)
assert b.allow() and b.allow() and b.allow()
assert not b.allow()
```
Token-bucket limiter with configurable refill rate and burst capacity; uses monotonic time and rejects invalid configuration.'''

    return None


def transaction_id(obj: Any) -> str:
    if isinstance(obj, dict):
        for key in ("transaction_id", "transactionId"):
            if obj.get(key):
                return str(obj[key])
        tx = obj.get("transaction")
        if isinstance(tx, dict) and tx.get("id"):
            return str(tx["id"])
        # Claim responses may themselves be transaction objects.
        if obj.get("id") and any(k in obj for k in ("status", "listing_id", "buyer_id", "seller_id")):
            return str(obj["id"])
        for value in obj.values():
            tid = transaction_id(value)
            if tid:
                return tid
    return ""


def claim(item: dict) -> Any:
    lid = listing_id(item)
    if not lid:
        raise RuntimeError("Listing has no id")
    return request("POST", f"/listings/{urllib.parse.quote(lid)}/claim", auth=True)


def deliver(tid: str, content: str) -> Any:
    # The public docs expose the endpoint but not a request-body example. Try only
    # non-destructive field-name variants, stopping immediately on first success.
    errors = []
    for payload in (
        {"deliverable": content},
        {"content": content},
        {"message": content},
    ):
        try:
            return request("POST", f"/transactions/{urllib.parse.quote(tid)}/deliver", payload=payload, auth=True)
        except RuntimeError as e:
            errors.append(str(e))
            if "HTTP 409" in str(e):
                raise
    raise RuntimeError("Deliver failed for all documented-compatible payload shapes: " + " | ".join(errors))


def main() -> int:
    payload = request("GET", "/listings?listing_type=BOUNTY")
    listings = flatten_listings(payload)
    candidates = []
    for item in listings:
        d = deterministic_deliverable(item)
        r = reward_usdc(item)
        if d is not None and r >= MIN_REWARD and listing_id(item):
            candidates.append((r, item, d))

    candidates.sort(key=lambda x: x[0], reverse=True)
    print(json.dumps({
        "mode": "LIVE" if LIVE else "DRY_RUN",
        "listings_seen": len(listings),
        "safe_candidates": [
            {"id": listing_id(i), "title": title(i), "reward_usdc": r}
            for r, i, _ in candidates
        ],
    }, indent=2))

    if not LIVE:
        return 0
    if not API_KEY:
        print("LIVE requested but CLAWLANCER_API_KEY is missing", file=sys.stderr)
        return 2

    completed = 0
    for reward, item, content in candidates:
        if completed >= MAX_CLAIMS:
            break
        print(f"Claiming {listing_id(item)} | ${reward:.4f} | {title(item)}")
        try:
            claim_result = claim(item)
            tid = transaction_id(claim_result)
            if not tid:
                print("Claim succeeded but no transaction id could be resolved; refusing to guess delivery target.")
                print(json.dumps(claim_result, indent=2)[:2000])
                continue
            result = deliver(tid, content)
            print("Delivered:", json.dumps(result)[:2000])
            completed += 1
        except Exception as e:
            print(f"Skipped after error: {e}", file=sys.stderr)

    print(f"completed_this_run={completed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
