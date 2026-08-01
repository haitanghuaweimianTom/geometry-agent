"""Dataset loader: read back annotation JSONs and images written by SynthGenerator.

Functions:
  * :func:`load_dataset`  -- read all ``*.json`` annotation records from a dir
  * :func:`load_image`    -- read a single image as an ``H x W x 3`` BGR array
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2


def load_dataset(path: str | Path) -> list[dict[str, Any]]:
    """Load all annotation JSON records from ``path``.

    ``path`` may be a directory (every ``*.json`` file is loaded, sorted by
    name) or a single JSON file containing either a list of records or one
    record object.
    """
    p = Path(path)
    records: list[dict[str, Any]] = []
    if p.is_dir():
        files = sorted(p.glob("*.json"))
        for f in files:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                records.extend(data)
            elif isinstance(data, dict):
                records.append(data)
        return records
    if p.is_file():
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    raise FileNotFoundError(f"No dataset found at {path}")


def load_image(path: str | Path) -> Any:
    """Read an image from ``path`` as an ``H x W x 3`` BGR uint8 ndarray.

    Raises ``FileNotFoundError`` if the file does not exist or cv2 fails.
    """
    p = str(path)
    img = cv2.imread(p, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Failed to read image: {path}")
    return img
