def money(v):
    if v is None or v == "":
        return 0
    s = str(v).replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except Exception:
        return 0


def score_signal(required, on_file, power_units=0, authority_status=""):
    gap = max(0, required - on_file)
    score = 0
    status = (authority_status or "").lower()

    if "pending" in status:
        score += 25
    elif "active" in status:
        score += 10

    if gap > 0:
        score += 35
    if gap >= 750000:
        score += 15
    if gap >= 1000000:
        score += 10

    try:
        pu = int(power_units or 0)
    except Exception:
        pu = 0

    if pu >= 5:
        score += 5
    if pu >= 20:
        score += 5
    if pu >= 100:
        score += 5

    return min(100, score)


def normalize_row(row):
    required = money(row.get("bipd_required") or row.get("BIPD_REQUIRED"))
    on_file = money(row.get("bipd_on_file") or row.get("BIPD_ON_FILE"))
    gap = max(0, required - on_file)

    authority_status = (
        row.get("authority_status")
        or row.get("AUTHORITY_STATUS")
        or row.get("common_authority_status")
        or ""
    )

    return {
        "usdot": str(row.get("usdot") or row.get("USDOT") or row.get("dot_number") or "").strip() or None,
        "legalName": row.get("legal_name") or row.get("LEGAL_NAME") or row.get("carrier_name"),
        "dbaName": row.get("dba_name") or row.get("DBA_NAME"),
        "state": row.get("state") or row.get("PHY_STATE"),
        "city": row.get("city") or row.get("PHY_CITY"),
        "phone": row.get("phone") or row.get("TELEPHONE"),
        "email": row.get("email") or row.get("EMAIL"),
        "powerUnits": int(float(row.get("power_units") or row.get("POWER_UNITS") or 0) or 0),
        "authorityStatus": authority_status,
        "bipdRequired": required,
        "bipdOnFile": on_file,
        "coverageGap": gap,
    }


def qualifies(row, min_gap=1):
    return row["coverageGap"] >= min_gap and row["bipdRequired"] > 0
