"""Small trade files make chunk-boundary mistakes easier to spot."""

from pathlib import Path
import tempfile
import unittest

import pandas as pd

from spy_data import build_minute_bars, validate_bars


def trade(time, price, size=1, condition="", correction="00"):
    return {"DATE": "2026-09-14", "TIME_M": time, "EX": "N", "SYM_ROOT": "SPY",
            "SYM_SUFFIX": "", "TR_SCOND": condition, "SIZE": str(size), "PRICE": str(price),
            "TR_STOP_IND": "N", "TR_CORR": correction, "TR_SEQNUM": time,
            "TR_ID": time, "TR_SOURCE": "C", "TR_RF": ""}


class MinuteBarChecks(unittest.TestCase):
    def test_duplicates_and_ohlc_across_chunks(self):
        rows = [trade("9:30:00.000000001", 100), trade("9:30:10", 102, 2),
                trade("9:30:10", 102, 2), trade("9:30:20", 101, 3),
                trade("9:31:00", 103, 4), trade("9:31:10", 0),
                trade("9:31:20", 104, condition="Z"),
                trade("9:31:30", 104, correction="07"), trade("16:00:00", 104)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trades.csv"
            pd.DataFrame(rows).to_csv(path, index=False)
            reference = None
            for chunk_size in [1, 2, 3, 100]:
                bars, audit = build_minute_bars(path, chunksize=chunk_size)
                if reference is not None:
                    pd.testing.assert_frame_equal(reference, bars)
                reference = bars
                first = bars.iloc[0]
                self.assertEqual((first["open"], first["high"], first["low"], first["close"]),
                                 (100, 102, 100, 101))
                self.assertEqual(first["volume"], 6)
                self.assertEqual(first["trades"], 3)
                self.assertAlmostEqual(first["vwap"], 607 / 6)
                self.assertEqual(audit["raw_rows"], 9)
                self.assertEqual(audit["kept_rows"], 4)
                for reason in ["duplicate_record", "invalid_price_or_size",
                               "sale_condition", "correction_or_cancel", "outside_session"]:
                    self.assertEqual(audit["removed"][reason], 1)

    def test_out_of_order_trades_are_not_silently_sorted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trades.csv"
            pd.DataFrame([trade("9:31:00", 101), trade("9:30:00", 100)]).to_csv(path, index=False)
            for chunk_size in [1, 100]:
                with self.assertRaisesRegex(ValueError, "out of time order"):
                    build_minute_bars(path, chunksize=chunk_size)

    def test_missing_minutes_are_not_filled(self):
        index = pd.date_range("2026-09-14 09:30", periods=390, freq="min", tz="America/New_York")
        bars = pd.DataFrame({"open": 100, "high": 101, "low": 99, "close": 100,
                             "vwap": 100, "volume": 10, "trades": 1}, index=index)
        validate_bars(bars)
        with self.assertRaisesRegex(ValueError, "missing minutes"):
            validate_bars(bars.drop(index[100]))


if __name__ == "__main__":
    unittest.main()
