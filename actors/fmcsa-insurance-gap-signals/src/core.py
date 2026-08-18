from datetime import datetime, timezone


def money_amount(v):
    """Normalize Motus monetary fields to dollars."""
    if v is None or v == "":
        return 0.0
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return 0.0


def score_signal(required, on_file, authority_status="", trigger="insurance-coverage-gap"):
    gap = max(0, required - on_file)
    score = 0
    status = (authority_status or "").lower()

    if "pending" in status:
        score += 30
    elif "active" in status:
        score += 10
    if gap > 0:
        score += 35
    if gap >= 750000:
        score += 15
    if gap >= 1000000:
        score += 10
    if required >= 5000000:
        score += 10
    if trigger in {
        "new-insurance-gap",
        "coverage-gap-widened",
        "authority-status-changed",
        "insurance-filing-changed",
    }:
        score += 10
    return min(100, score)


def normalize_row(row):
    required = money_amount(row.get("min_cov_amount"))
    on_file = money_amount(row.get("bipd_file"))
    return {
        "docketNumber": row.get("docket_number"),
        "usdot": str(row.get("usdot_number") or "").strip() or None,
        "legalName": row.get("legal_name"),
        "dbaName": row.get("dba_name"),
        "authorityType": row.get("op_auth_type"),
        "authorityStatus": row.get("op_auth_status") or "",
        "bipdRequired": required,
        "bipdOnFile": on_file,
        "coverageGap": max(0, required - on_file),
        "cargoRequired": row.get("cargo_req"),
        "cargoOnFile": row.get("cargo_file"),
        "bondRequired": row.get("bond_req"),
        "bondOnFile": row.get("bond_file"),
    }


def qualifies(row, min_gap=1):
    return row["bipdRequired"] > 0 and row["coverageGap"] >= min_gap


def carrier_key(row):
    authority = row.get("authorityType") or ""
    if row.get("docketNumber"):
        return f"docket:{row['docketNumber']}|auth:{authority}"
    if row.get("usdot"):
        return f"usdot:{row['usdot']}|auth:{authority}"
    return f"name:{row.get('legalName') or ''}|auth:{authority}"


def snapshot_row(row):
    return {
        "authorityStatus": row.get("authorityStatus") or "",
        "bipdRequired": row.get("bipdRequired") or 0,
        "bipdOnFile": row.get("bipdOnFile") or 0,
        "coverageGap": row.get("coverageGap") or 0,
        "cargoOnFile": row.get("cargoOnFile"),
        "bondOnFile": row.get("bondOnFile"),
    }


def detect_changes(row, previous):
    """Return deterministic, buyer-relevant changes for one deficient authority."""
    if not previous:
        return ["new-insurance-gap"]

    changes = []
    old_gap = money_amount(previous.get("coverageGap"))
    new_gap = money_amount(row.get("coverageGap"))
    if new_gap > old_gap:
        changes.append("coverage-gap-widened")
    elif new_gap < old_gap:
        changes.append("coverage-gap-narrowed")

    if (previous.get("authorityStatus") or "") != (row.get("authorityStatus") or ""):
        changes.append("authority-status-changed")
    if money_amount(previous.get("bipdOnFile")) != money_amount(row.get("bipdOnFile")):
        changes.append("insurance-filing-changed")
    if previous.get("cargoOnFile") != row.get("cargoOnFile"):
        changes.append("cargo-filing-changed")
    if previous.get("bondOnFile") != row.get("bondOnFile"):
        changes.append("bond-filing-changed")
    return changes


def enrich_signal(row, trigger, previous=None):
    out = dict(row)
    out["trigger"] = trigger
    out["signalScore"] = score_signal(
        out["bipdRequired"], out["bipdOnFile"], out["authorityStatus"], trigger
    )
    out["detectedAt"] = datetime.now(timezone.utc).isoformat()
    out["previousAuthorityStatus"] = (previous or {}).get("authorityStatus")
    out["previousCoverageGap"] = (previous or {}).get("coverageGap")
    out["previousBipdOnFile"] = (previous or {}).get("bipdOnFile")
    return out
