"""Structured logging helper (see design/11-Engineering.md §6)."""
from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager
from typing import Any


def _emit(record: dict[str, Any]) -> None:
    print(json.dumps(record, ensure_ascii=False, default=str), file=sys.stderr, flush=True)


@contextmanager
def log_step(module: str, step: str, **extra: Any):
    """Context manager logging a step's duration and result.

    Usage:
        with log_step("parser", "deskew", input_hash=h) as log:
            result = ...
            log(result_summary=...)
    """
    start = time.perf_counter()
    record: dict[str, Any] = {"module": module, "step": step, "ts": time.time(), **extra}
    try:
        yield record
    except Exception as e:
        record["error"] = repr(e)
        record["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        _emit(record)
        raise
    else:
        record["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        _emit(record)


def info(module: str, step: str, **extra: Any) -> None:
    _emit({"module": module, "step": step, "ts": time.time(), **extra})
