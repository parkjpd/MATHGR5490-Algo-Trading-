"""Read the large trade file without keeping the whole thing in memory."""

from pathlib import Path
import hashlib
import json
from collections import Counter

import numpy as np
import pandas as pd


RAW_NAMES = ("qykjkjsbk5ycr4qh.csv", "wyibfmmayut9nuxe.csv")
BAR_FILE = Path("data/spy_1min.csv")
AUDIT_FILE = Path("data/cleaning_audit.json")
PIPELINE_VERSION = 1


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_raw_files(root):
    paths = [Path(root) / name for name in RAW_NAMES]
    paths = [path for path in paths if path.exists()]
    if not paths:
        raise FileNotFoundError("Put either raw SPY CSV next to the notebook to rebuild the bars.")
    manifest = [{"file": path.name, "bytes": path.stat().st_size,
                 "sha256": file_hash(path)} for path in paths]
    # Matching hashes mean this is the same download twice.
    return paths[0], manifest


def clean_chunks(path, audit, chunksize=250_000):
    columns = ["DATE", "TIME_M", "EX", "SYM_ROOT", "SYM_SUFFIX", "TR_SCOND",
               "SIZE", "PRICE", "TR_STOP_IND", "TR_CORR", "TR_SEQNUM",
               "TR_ID", "TR_SOURCE", "TR_RF"]
    previous_time = None
    boundary_hashes = set()
    conditions = Counter()
    removed = Counter()
    for raw in pd.read_csv(path, usecols=columns, dtype="string",
                           keep_default_na=False, chunksize=chunksize):
        audit["raw_rows"] = audit.get("raw_rows", 0) + len(raw)
        conditions.update(raw["TR_SCOND"].value_counts().to_dict())
        chunk = raw.copy()

        def keep(mask, reason):
            nonlocal chunk
            removed[reason] += int((~mask).sum())
            chunk = chunk.loc[mask].copy()

        keep(chunk["SYM_ROOT"].eq("SPY") & chunk["SYM_SUFFIX"].eq(""), "other_symbol")
        chunk["timestamp"] = pd.to_datetime(
            chunk["DATE"] + " " + chunk["TIME_M"], format="mixed", errors="coerce")
        keep(chunk["timestamp"].notna(), "invalid_timestamp")
        if chunk.empty:
            continue
        # Sorting a chunk alone wouldn't fix a file that's out of order between chunks.
        if (not chunk["timestamp"].is_monotonic_increasing or
                (previous_time is not None and chunk["timestamp"].iloc[0] < previous_time)):
            raise ValueError("Raw trades are out of time order; sort the source before building bars.")

        hashes = pd.util.hash_pandas_object(chunk[columns], index=False)
        duplicate = hashes.duplicated() | hashes.isin(boundary_hashes)
        last_time = chunk["timestamp"].iloc[-1]
        last_hashes = set(hashes[chunk["timestamp"].eq(last_time)])
        boundary_hashes = boundary_hashes | last_hashes if last_time == previous_time else last_hashes
        previous_time = last_time
        keep(~duplicate, "duplicate_record")

        chunk["PRICE"] = pd.to_numeric(chunk["PRICE"], errors="coerce").astype(float)
        chunk["SIZE"] = pd.to_numeric(chunk["SIZE"], errors="coerce").astype(float)
        keep(np.isfinite(chunk["PRICE"]) & np.isfinite(chunk["SIZE"]) &
             chunk["PRICE"].gt(0) & chunk["SIZE"].gt(0), "invalid_price_or_size")
        keep(chunk["TR_CORR"].eq("00"), "correction_or_cancel")
        keep(chunk["TR_STOP_IND"].isin(["N", ""]), "stopped_trade")
        # Keep regular prints, sweeps, odd lots, and opening/cross prints.
        # Late reports and reference/average prices don't belong in the minute close.
        keep(chunk["TR_SCOND"].str.fullmatch(r"[EFIOQX@ ]*"), "sale_condition")
        minutes = chunk["timestamp"].dt.hour * 60 + chunk["timestamp"].dt.minute
        keep(minutes.ge(570) & minutes.lt(960), "outside_session")
        audit["kept_rows"] = audit.get("kept_rows", 0) + len(chunk)
        if not chunk.empty:
            yield chunk
    audit["removed"] = dict(removed)
    audit["sale_conditions_raw"] = dict(conditions.most_common())


def build_minute_bars(path, chunksize=250_000):
    audit = {"raw_rows": 0, "kept_rows": 0}
    parts = []
    for chunk in clean_chunks(path, audit, chunksize):
        chunk["bar_time"] = chunk["timestamp"].dt.floor("min")
        chunk["price_volume"] = chunk["PRICE"] * chunk["SIZE"]
        parts.append(chunk.groupby("bar_time", sort=True).agg(
            open=("PRICE", "first"), high=("PRICE", "max"),
            low=("PRICE", "min"), close=("PRICE", "last"),
            volume=("SIZE", "sum"), price_volume=("price_volume", "sum"),
            trades=("PRICE", "size")))
    if not parts:
        raise ValueError("No usable SPY trades remain after cleaning.")
    # A minute can straddle a chunk boundary. Keep the original first/last order.
    partial = pd.concat(parts)
    bars = partial.groupby(level=0, sort=True).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"),
        price_volume=("price_volume", "sum"), trades=("trades", "sum"))
    bars["vwap"] = bars.pop("price_volume") / bars["volume"]
    bars.index = bars.index.tz_localize("America/New_York")
    bars.index.name = "bar_time"
    audit.update({"bars": len(bars), "sessions": bars.index.normalize().nunique(),
                  "first_bar": str(bars.index[0]), "last_bar": str(bars.index[-1]),
                  "timezone": "America/New_York", "bar_minutes": 1})
    assert audit["raw_rows"] == audit["kept_rows"] + sum(audit["removed"].values())
    assert bars["trades"].sum() == audit["kept_rows"]
    return bars, audit


def validate_bars(bars):
    assert len(bars) > 0 and bars.index.is_unique and bars.index.is_monotonic_increasing
    assert str(bars.index.tz) == "America/New_York"
    assert np.isfinite(bars.to_numpy()).all(), "A bar contains a missing or infinite value."
    assert bars[["open", "high", "low", "close", "vwap", "volume", "trades"]].gt(0).all().all()
    assert bars["high"].ge(bars[["open", "close", "low", "vwap"]].max(axis=1)).all()
    assert bars["low"].le(bars[["open", "close", "high", "vwap"]].min(axis=1)).all()
    for _, day in bars.groupby(bars.index.normalize()):
        expected = pd.date_range(day.index[0].normalize() + pd.Timedelta(hours=9, minutes=30),
                                 periods=390, freq="min")
        if not day.index.equals(expected):
            raise ValueError("This sample expects full 390-minute sessions. Check missing minutes or an early close; don't fill prices silently.")


def load_bars(root, rebuild=False):
    root = Path(root)
    bar_path, audit_path = root / BAR_FILE, root / AUDIT_FILE
    if not rebuild and bar_path.exists() and audit_path.exists():
        audit = json.loads(audit_path.read_text())
        if audit.get("pipeline_version") != PIPELINE_VERSION:
            raise ValueError("The cache was made with different cleaning rules. Set REBUILD=True.")
        if file_hash(bar_path) != audit["bar_sha256"]:
            raise ValueError("The bar CSV changed after it was built. Set REBUILD=True.")
        bars = pd.read_csv(bar_path, index_col="bar_time")
        bars.index = pd.to_datetime(bars.index, utc=True).tz_convert("America/New_York")
        bars.index.name = "bar_time"
    else:
        raw, manifest = find_raw_files(root)
        bars, audit = build_minute_bars(raw)
        audit.update({"sources": manifest, "source_used": raw.name,
                      "pipeline_version": PIPELINE_VERSION,
                      "duplicate_download": len({item["sha256"] for item in manifest}) < len(manifest)})
        validate_bars(bars)
        bar_path.parent.mkdir(parents=True, exist_ok=True)
        bars.to_csv(bar_path)
        audit["bar_sha256"] = file_hash(bar_path)
        audit_path.write_text(json.dumps(audit, indent=2) + "\n")
    validate_bars(bars)
    assert len(bars) == audit["bars"]
    assert bars["trades"].sum() == audit["kept_rows"]
    return bars, audit
