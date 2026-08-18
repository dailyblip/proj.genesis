def money_thousands(v):
    if v is None or v == "":
        return 0.0
    try:
        return float(str(v).replace(",", "").strip()) * 1000
    except Exception:
        return 0.0


def score_signal(required, on_file, authority_status=""):
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

    return min(100, score)


def normalize_row(row):
    required = money_thousands(row.get("min_cov_amount"))
    on_file = money_thousands(row.get("bipd_file"))

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
