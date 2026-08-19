from collections import Counter
from datetime import date, timedelta
from math import log1p


def key_rows(rows):
    counts = Counter()
    for r in rows:
        company = (r.get("company") or "").strip()
        product = (r.get("product") or "").strip()
        if company:
            counts[(company, product)] += 1
    return counts


def make_signals(current_rows, baseline_rows, current_days=7, baseline_days=28,
                 min_current=10, min_ratio=2.0, max_signals=50):
    cur, base = key_rows(current_rows), key_rows(baseline_rows)
    scale = current_days / baseline_days
    signals = []
    for (company, product), current in cur.items():
        expected = base.get((company, product), 0) * scale
        ratio = current / max(expected, 1.0)
        excess = current - expected
        if current < min_current or ratio < min_ratio or excess <= 0:
            continue
        score = ratio * log1p(current) * log1p(excess)
        signals.append({
            "company": company,
            "product": product,
            "currentComplaints": current,
            "baselineExpected": round(expected, 2),
            "spikeRatio": round(ratio, 2),
            "excessComplaints": round(excess, 2),
            "signalScore": round(score, 2),
        })
    signals.sort(key=lambda x: (x["signalScore"], x["currentComplaints"]), reverse=True)
    return signals[:max_signals]


def windows(current_days=7, baseline_days=28, today=None):
    today = today or date.today()
    current_end = today
    current_start = current_end - timedelta(days=current_days - 1)
    baseline_end = current_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=baseline_days - 1)
    return current_start, current_end, baseline_start, baseline_end
