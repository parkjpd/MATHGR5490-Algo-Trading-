"""Read the large trade file without keeping the whole thing in memory."""

from pathlib import Path
import hashlib
import json

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
