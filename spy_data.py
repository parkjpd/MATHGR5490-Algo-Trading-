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
