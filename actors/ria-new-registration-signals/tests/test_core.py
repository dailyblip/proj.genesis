import pandas as pd

from src.core import find_column, new_rows, normalize_signal


def test_new_rows_by_crd():
    latest = pd.DataFrame({"CRD Number": ["1", "2", "3"], "Primary Business Name": ["A", "B", "C"]})
    previous = pd.DataFrame({"CRD Number": ["1", "3"], "Primary Business Name": ["A", "C"]})
    result = new_rows(latest, previous)
    assert result["CRD Number"].tolist() == ["2"]


def test_column_alias_matching():
    df = pd.DataFrame(columns=["Firm CRD Number", "Primary Business Name"])
    assert find_column(df, ["CRD Number", "Firm CRD Number"]) == "Firm CRD Number"


def test_normalize_signal_scores_contactable_firm():
    df = pd.DataFrame([
        {
            "CRD Number": "123",
            "Primary Business Name": "Example Advisers LLC",
            "Regulatory Assets Under Management": "$1,250,000,000",
            "Main Office State": "CA",
            "Main Office City": "San Francisco",
            "Main Office Telephone Number": "415-555-1212",
            "Website Address": "https://example.com",
        }
    ])
    signal = normalize_signal(df.iloc[0], df, "July 2026", "June 2026")
    assert signal["crdNumber"] == "123"
    assert signal["regulatoryAum"] == 1250000000.0
    assert signal["signalScore"] == 100
