import io
import re
import zipfile
from datetime import datetime, timezone

import pandas as pd


def norm_col(name):
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def read_sec_zip(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        members = [m for m in zf.namelist() if not m.endswith("/")]
        if not members:
            raise ValueError("SEC archive is empty")
        preferred = sorted(
            members,
            key=lambda m: (0 if m.lower().endswith(".xlsx") else 1 if m.lower().endswith(".csv") else 2, m),
        )[0]
        raw = zf.read(preferred)
        if preferred.lower().endswith(".xlsx"):
            return pd.read_excel(io.BytesIO(raw), dtype=str)
        if preferred.lower().endswith(".csv"):
            return pd.read_csv(io.BytesIO(raw), dtype=str, low_memory=False)
        raise ValueError(f"Unsupported SEC archive member: {preferred}")


def find_column(df, aliases):
    cols = {norm_col(c): c for c in df.columns}
    for alias in aliases:
        key = norm_col(alias)
        if key in cols:
            return cols[key]
    for alias in aliases:
        key = norm_col(alias)
        for n, original in cols.items():
            if key and key in n:
                return original
    return None


def pick(row, df, aliases):
    col = find_column(df, aliases)
    if not col:
        return None
    value = row.get(col)
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def money(value):
    if value is None:
        return None
    text = re.sub(r"[^0-9.\-]", "", str(value))
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def crd_column(df):
    return find_column(df, ["CRD Number", "CRD No", "Firm CRD Number", "Primary Business Name CRD"])


def new_rows(latest: pd.DataFrame, previous: pd.DataFrame) -> pd.DataFrame:
    latest_crd = crd_column(latest)
    previous_crd = crd_column(previous)
    if not latest_crd or not previous_crd:
        raise ValueError("Could not identify CRD number column in SEC data")
    prior = set(previous[previous_crd].dropna().astype(str).str.strip())
    mask = ~latest[latest_crd].fillna("").astype(str).str.strip().isin(prior)
    return latest.loc[mask].copy()


def normalize_signal(row, df, latest_label, previous_label):
    crd = pick(row, df, ["CRD Number", "CRD No", "Firm CRD Number"])
    name = pick(row, df, ["Primary Business Name", "Legal Name", "Organization Name", "Firm Name"])
    aum = money(pick(row, df, ["Regulatory Assets Under Management", "RAUM", "5F(2)(c)", "Assets Under Management"]))
    employees = pick(row, df, ["Number of Employees", "5A", "Employees"])
    city = pick(row, df, ["Main Office City", "City"])
    state = pick(row, df, ["Main Office State", "State"])
    phone = pick(row, df, ["Main Office Telephone Number", "Telephone Number", "Phone"])
    website = pick(row, df, ["Website Address", "Website"])
    sec_number = pick(row, df, ["SEC Number", "SEC File Number"])
    filing_date = pick(row, df, ["Latest ADV Filing Date", "Date of Filing", "Filing Date"])

    score = 45
    if aum is not None:
        if aum >= 1_000_000_000:
            score += 30
        elif aum >= 250_000_000:
            score += 20
        elif aum >= 100_000_000:
            score += 10
    if phone:
        score += 10
    if website:
        score += 10
    if state:
        score += 5

    return {
        "trigger": "new-sec-registered-investment-adviser",
        "signalScore": min(score, 100),
        "crdNumber": crd,
        "secNumber": sec_number,
        "firmName": name,
        "filingDate": filing_date,
        "city": city,
        "state": state,
        "phone": phone,
        "website": website,
        "regulatoryAum": aum,
        "employees": employees,
        "latestDataset": latest_label,
        "previousDataset": previous_label,
        "detectedAt": datetime.now(timezone.utc).isoformat(),
        "source": "SEC Investment Adviser Information Reports",
        "sourceUrl": "https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers",
    }
