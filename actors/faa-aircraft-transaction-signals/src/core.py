from __future__ import annotations

from datetime import date, datetime

REGISTRANT_TYPES = {
    "1": "Individual",
    "2": "Partnership",
    "3": "Corporation",
    "4": "Co-Owned",
    "5": "Government",
    "7": "LLC",
    "8": "Non-Citizen Corporation",
    "9": "Non-Citizen Co-Owned",
}

AIRCRAFT_TYPES = {
    "1": "Glider", "2": "Balloon", "3": "Blimp/Dirigible",
    "4": "Fixed wing single engine", "5": "Fixed wing multi engine",
    "6": "Rotorcraft", "7": "Weight-shift-control", "8": "Powered Parachute",
    "9": "Gyroplane", "H": "Hybrid Lift", "O": "Other",
}

ENGINE_TYPES = {
    "0": "None", "1": "Reciprocating", "2": "Turbo-prop", "3": "Turbo-shaft",
    "4": "Turbo-jet", "5": "Turbo-fan", "6": "Ramjet", "7": "2 Cycle",
    "8": "4 Cycle", "9": "Unknown", "10": "Electric", "11": "Rotary",
}

STATUS_CODES = {
    "R": "Registration pending", "V": "Valid Registration", "7": "Sale reported",
    "M": "Manufacturer dealer registration", "W": "Registration ineffective/invalid",
    "X": "Enforcement letter", "6": "Administratively canceled", "9": "Registration revoked",
}


def clean_row(row: dict) -> dict:
    return {str(k).strip().upper(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k is not None}


def pick(row: dict, *names: str, default=""):
    for name in names:
        value = row.get(name.upper())
        if value not in (None, ""):
            return value
    return default


def parse_faa_date(value: str):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y%m%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def iso_date(value: str):
    d = parse_faa_date(value)
    return d.isoformat() if d else None


def year_int(value):
    try:
        y = int(str(value).strip())
        return y if 1900 <= y <= 2100 else None
    except Exception:
        return None


def score_signal(row: dict, today: date, lookback_days: int):
    status_code = str(pick(row, "STATUS CODE", "STATUS_CODE", "STATUS")).strip()
    reg_type_code = str(pick(row, "TYPE REGISTRANT", "TYPE_REGISTRANT")).strip()
    engine_code = str(pick(row, "TYPE ENGINE", "TYPE_ENGINE")).strip()
    aircraft_code = str(pick(row, "TYPE AIRCRAFT", "TYPE_AIRCRAFT")).strip()
    last_activity = parse_faa_date(str(pick(row, "LAST ACTION DATE", "LAST ACTIVITY DATE", "LAST_ACTION_DATE")))
    cert_issue = parse_faa_date(str(pick(row, "CERT ISSUE DATE", "CERTIFICATE ISSUE DATE", "CERT_ISSUE_DATE")))

    recent_activity = last_activity is not None and 0 <= (today - last_activity).days <= lookback_days
    recent_cert = cert_issue is not None and 0 <= (today - cert_issue).days <= lookback_days
    sale_reported = status_code == "7"

    if not (sale_reported or recent_activity or recent_cert):
        return None

    score = 35
    reasons = []
    signal_type = "recent-registry-activity"

    if sale_reported:
        score += 30
        reasons.append("FAA status shows sale reported")
        signal_type = "sale-reported"
    if recent_cert:
        score += 20
        reasons.append("registration certificate issued recently")
        if not sale_reported:
            signal_type = "recent-registration"
    elif recent_activity:
        score += 10
        reasons.append("FAA registry activity is recent")

    if reg_type_code in {"2", "3", "7", "8"}:
        score += 10
        reasons.append("business registrant")
    if engine_code in {"2", "3", "4", "5"}:
        score += 20
        reasons.append("turbine-powered aircraft")
    if aircraft_code == "5":
        score += 8
        reasons.append("multi-engine aircraft")

    year = year_int(pick(row, "YEAR MFR", "YEAR_MFR"))
    if year and year >= today.year - 10:
        score += 7
        reasons.append("relatively recent manufacture year")

    return min(score, 100), signal_type, reasons


def is_business_registrant(row: dict) -> bool:
    code = str(pick(row, "TYPE REGISTRANT", "TYPE_REGISTRANT")).strip()
    return code in {"2", "3", "7", "8"}


def normalize_signal(row: dict, aircraft_refs: dict, score: int, signal_type: str, reasons: list[str]) -> dict:
    mfr_code = str(pick(row, "MFR MDL CODE", "MFR_MDL_CODE", "AIRCRAFT MFR MODEL CODE")).strip()
    ref = aircraft_refs.get(mfr_code, {})
    reg_code = str(pick(row, "TYPE REGISTRANT", "TYPE_REGISTRANT")).strip()
    aircraft_code = str(pick(row, "TYPE AIRCRAFT", "TYPE_AIRCRAFT")).strip()
    engine_code = str(pick(row, "TYPE ENGINE", "TYPE_ENGINE")).strip()
    status_code = str(pick(row, "STATUS CODE", "STATUS_CODE", "STATUS")).strip()
    n = str(pick(row, "N-NUMBER", "N NUMBER", "N_NUMBER")).strip()

    return {
        "signalScore": score,
        "signalType": signal_type,
        "signalReasons": reasons,
        "nNumber": f"N{n}" if n and not n.upper().startswith("N") else n,
        "ownerName": pick(row, "NAME", "REGISTRANT NAME", "OWNER NAME") or None,
        "registrantType": REGISTRANT_TYPES.get(reg_code, reg_code or None),
        "city": pick(row, "CITY", "REGISTRANT CITY") or None,
        "state": pick(row, "STATE", "REGISTRANT STATE") or None,
        "aircraftMake": ref.get("make") or None,
        "aircraftModel": ref.get("model") or None,
        "yearManufactured": year_int(pick(row, "YEAR MFR", "YEAR_MFR")),
        "aircraftType": AIRCRAFT_TYPES.get(aircraft_code, aircraft_code or None),
        "engineType": ENGINE_TYPES.get(engine_code, engine_code or None),
        "lastActivityDate": iso_date(str(pick(row, "LAST ACTION DATE", "LAST ACTIVITY DATE", "LAST_ACTION_DATE"))),
        "certificateIssueDate": iso_date(str(pick(row, "CERT ISSUE DATE", "CERTIFICATE ISSUE DATE", "CERT_ISSUE_DATE"))),
        "status": STATUS_CODES.get(status_code, status_code or None),
        "source": "FAA Releasable Aircraft Registry",
        "sourceUrl": "https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/releasable_aircraft_download",
    }
