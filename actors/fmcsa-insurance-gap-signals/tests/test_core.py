import unittest

from src.core import carrier_key, detect_changes, normalize_row, score_signal


class CoreTests(unittest.TestCase):
    def test_normalize_and_key(self):
        row = normalize_row({
            "docket_number": "MC123",
            "usdot_number": "456",
            "op_auth_type": "CARRIER",
            "op_auth_status": "ACTIVE",
            "min_cov_amount": "750000",
            "bipd_file": "500000",
        })
        self.assertEqual(row["coverageGap"], 250000)
        self.assertEqual(carrier_key(row), "docket:MC123|auth:CARRIER")

    def test_new_gap(self):
        row = {"coverageGap": 250000, "authorityStatus": "ACTIVE", "bipdOnFile": 500000,
               "cargoOnFile": None, "bondOnFile": None}
        self.assertEqual(detect_changes(row, None), ["new-insurance-gap"])

    def test_multiple_changes(self):
        previous = {
            "coverageGap": 100000,
            "authorityStatus": "PENDING",
            "bipdOnFile": 650000,
            "cargoOnFile": "N",
            "bondOnFile": "N",
        }
        row = {
            "coverageGap": 250000,
            "authorityStatus": "ACTIVE",
            "bipdOnFile": 500000,
            "cargoOnFile": "Y",
            "bondOnFile": "N",
        }
        changes = detect_changes(row, previous)
        self.assertIn("coverage-gap-widened", changes)
        self.assertIn("authority-status-changed", changes)
        self.assertIn("insurance-filing-changed", changes)
        self.assertIn("cargo-filing-changed", changes)

    def test_change_boost_is_capped(self):
        self.assertLessEqual(score_signal(5000000, 0, "PENDING", "new-insurance-gap"), 100)


if __name__ == "__main__":
    unittest.main()
