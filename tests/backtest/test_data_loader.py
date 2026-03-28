from __future__ import annotations

import pandas as pd

from backend.backtest.data_loader import load_from_csv, save_to_csv


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50, freq="h", tz="UTC"),
        "open": [65000.0] * 50,
        "high": [65200.0] * 50,
        "low": [64800.0] * 50,
        "close": [65100.0] * 50,
        "volume": [100.0] * 50,
    })


class TestCSVRoundTrip:
    def test_save_and_load_csv(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        df = _sample_df()

        save_to_csv(df, csv_path)
        loaded = load_from_csv(csv_path)

        assert len(loaded) == 50
        assert list(loaded.columns) == list(df.columns)
        assert loaded["close"].iloc[0] == 65100.0

    def test_load_csv_with_tz(self, tmp_path):
        csv_path = tmp_path / "tz_test.csv"
        df = _sample_df()
        save_to_csv(df, csv_path)
        loaded = load_from_csv(csv_path)

        assert loaded["timestamp"].dt.tz is not None

    def test_save_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "a" / "b" / "data.csv"
        df = _sample_df()
        save_to_csv(df, nested)
        assert nested.exists()
