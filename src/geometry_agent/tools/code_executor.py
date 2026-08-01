"""Sandboxed Python code executor for the Geometry Agent.

Why this exists
---------------
Geometry problems routinely need a trustworthy calculator: numerical work
(numpy), symbolic manipulation (sympy) and small geometry machine-proofs.
Sending those to the LLM is unreliable; executing validated code locally is
not. This module runs user/LLM-supplied Python in a *restricted* namespace:

* Pre-injected safe modules: ``math``, ``numpy as np``, ``sympy as sp``,
  ``fractions``, ``decimal``, ``statistics``.
* ``__builtins__`` is replaced by an explicit whitelist (``len``, ``range``,
  ``print``, ``abs`` ...); dangerous names (``__import__``, ``eval``,
  ``exec``, ``open``, ``compile`` ...) are absent.
* Import statements are intercepted via a custom ``__import__`` shim that
  only resolves names in ``CodeExecConfig.allow_imports``.
* ``stdout`` is captured via ``contextlib.redirect_stdout``.
* A wall-clock timeout is enforced with ``signal.alarm`` on Unix; on
  non-Unix platforms the timeout is reported but not enforced (graceful
  degradation).
* Captured output is truncated to ``max_output_chars``.

The executor is intentionally process-free: it runs in the caller's process
so Pydantic / sympy state stays shareable, with the safety net above.
"""

from __future__ import annotations

import builtins as _builtins
import contextlib
import io
import math
import signal
from typing import Any

import sympy as sp

try:
    import numpy as np
except Exception:  # pragma: no cover - numpy is a hard dependency
    np = None  # type: ignore[assignment]

import decimal
import fractions
import statistics

from geometry_agent.config import CodeExecConfig
from geometry_agent.types import CodeResult


# --------------------------------------------------------------------------- #
# Builtins whitelist: everything the executor is allowed to expose to user code.
# --------------------------------------------------------------------------- #
_SAFE_BUILTIN_NAMES: tuple[str, ...] = (
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
    "callable", "chr", "complex", "dict", "divmod", "enumerate", "filter",
    "float", "format", "frozenset", "getattr", "hasattr", "hash", "hex",
    "id", "int", "isinstance", "issubclass", "iter", "len", "list", "map",
    "max", "min", "next", "object", "oct", "ord", "pow", "print", "property",
    "range", "repr", "reversed", "round", "set", "setattr", "slice", "sorted",
    "str", "sum", "tuple", "type", "zip", "True", "False", "None",
    "Exception", "ValueError", "TypeError", "ZeroDivisionError",
    "IndexError", "KeyError", "AttributeError", "RuntimeError",
    "StopIteration", "ArithmeticError", "OverflowError", "NameError",
    "NotImplementedError", "AssertionError",
)


class _TimeoutError(Exception):
    """Raised internally when the wall-clock budget is exhausted."""


def _make_safe_builtins(allowed_imports: list[str]) -> dict[str, Any]:
    """Build a restricted ``__builtins__`` dict with a guarded ``__import__``."""

    real_import = _builtins.__import__

    def _guarded_import(name: str, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".")[0]
        if root not in allowed_imports:
            raise ImportError(
                f"import of {name!r} is not allowed; "
                f"permitted: {allowed_imports}"
            )
        return real_import(name, globals, locals, fromlist, level)

    safe: dict[str, Any] = {"__import__": _guarded_import}
    for n in _SAFE_BUILTIN_NAMES:
        if hasattr(_builtins, n):
            safe[n] = getattr(_builtins, n)
    return safe


def _build_namespace(config: CodeExecConfig) -> dict[str, Any]:
    """Construct the globals dict that user code executes against."""
    ns: dict[str, Any] = {
        "__builtins__": _make_safe_builtins(config.allow_imports),
        "math": math,
        "np": np,
        "sp": sp,
        "sympy": sp,
        "fractions": fractions,
        "decimal": decimal,
        "statistics": statistics,
    }
    return ns


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text) - limit} chars omitted]"


class CodeExecutor:
    """Run untrusted Python snippets in a restricted namespace."""

    def __init__(self, config: CodeExecConfig | None = None) -> None:
        self.config = config or CodeExecConfig()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def execute(self, code: str) -> CodeResult:
        """Execute ``code`` and return a :class:`CodeResult`.

        The code runs in a fresh namespace each call. ``stdout`` is captured;
        the value of a trailing expression statement (if any) is recorded in
        ``CodeResult.value``. Exceptions and timeouts are reported in
        ``CodeResult.error`` with ``success=False``.
        """
        if not self.config.enabled:
            return CodeResult(
                success=False,
                error="code execution disabled by config",
                code=code,
            )
        return self._run(code, enforce_safety=True)

    def execute_safe(self, code: str) -> CodeResult:
        """Alias of :meth:`execute`; always enforces the full safety policy."""
        return self._run(code, enforce_safety=True)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _run(self, code: str, *, enforce_safety: bool) -> CodeResult:
        ns = _build_namespace(self.config)
        buf = io.StringIO()
        value: Any = None
        try:
            with contextlib.redirect_stdout(buf):
                value = self._exec_with_timeout(code, ns)
        except _TimeoutError as exc:
            return CodeResult(
                success=False,
                output=_truncate(buf.getvalue(), self.config.max_output_chars),
                error=f"timeout: {exc}",
                code=code,
            )
        except ImportError as exc:
            return CodeResult(
                success=False,
                output=_truncate(buf.getvalue(), self.config.max_output_chars),
                error=f"blocked import: {exc}",
                code=code,
            )
        except BaseException as exc:  # noqa: BLE001 - we *want* to catch all
            return CodeResult(
                success=False,
                output=_truncate(buf.getvalue(), self.config.max_output_chars),
                error=f"{type(exc).__name__}: {exc}",
                code=code,
            )

        return CodeResult(
            success=True,
            output=_truncate(buf.getvalue(), self.config.max_output_chars),
            error="",
            value=self._jsonify(value),
            code=code,
        )

    def _exec_with_timeout(self, code: str, ns: dict[str, Any]) -> Any:
        """Compile+exec the code; return trailing expression value if any.

        Strategy (IPython-style): parse the source with :mod:`ast`. If the
        last top-level statement is an :class:`ast.Expr`, exec everything
        *but* the last statement in ``'exec'`` mode, then ``eval`` the last
        expression separately so its value can be captured for
        ``CodeResult.value`` (and pretty-printed via ``sys.displayhook``).
        Otherwise, exec the whole module in ``'exec'`` mode.

        ``signal.alarm`` enforces the wall-clock budget on Unix.
        """
        import ast
        import sys

        timeout = self.config.timeout_sec
        use_signal = hasattr(signal, "SIGALRM") and timeout > 0

        def _alarm_handler(signum, frame):  # noqa: ARG001
            raise _TimeoutError(f"exceeded {timeout}s budget")

        old_handler = None
        if use_signal:
            old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
            signal.setitimer(signal.ITIMER_REAL, float(timeout))

        try:
            try:
                tree = ast.parse(code, "<sandbox>", "exec")
            except (SyntaxError, IndentationError) as exc:
                raise type(exc)(str(exc)) from exc

            last = tree.body[-1] if tree.body else None
            trailing_expr: ast.Expression | None = None
            if isinstance(last, ast.Expr):
                trailing_expr = ast.Expression(body=last.value)
                ast.fix_missing_locations(trailing_expr)
                tree.body = tree.body[:-1]

            captured: dict[str, Any] = {"value": None}

            def _hook(obj):
                captured["value"] = obj
                if obj is not None:
                    print(repr(obj))

            old_hook = sys.displayhook
            sys.displayhook = _hook
            try:
                if tree.body:
                    exec(compile(tree, "<sandbox>", "exec"), ns)  # noqa: S102
                if trailing_expr is not None:
                    val = eval(compile(trailing_expr, "<sandbox>", "eval"), ns)  # noqa: S307
                    _hook(val)
            finally:
                sys.displayhook = old_hook
            return captured["value"]
        finally:
            if use_signal:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old_handler)

    @staticmethod
    def _jsonify(value: Any) -> Any:
        """Best-effort conversion of an arbitrary value to a JSON-able form."""
        if value is None:
            return None
        # sympy objects -> pretty string
        if hasattr(value, "simplify") and hasattr(value, "free_symbols"):
            try:
                return str(value)
            except Exception:  # pragma: no cover
                return repr(value)
        if isinstance(value, (int, float, str, bool)):
            return value
        if isinstance(value, (list, tuple)):
            return [CodeExecutor._jsonify(v) for v in value]
        if isinstance(value, dict):
            return {str(k): CodeExecutor._jsonify(v) for k, v in value.items()}
        try:
            import numpy as _np

            if isinstance(value, _np.ndarray):
                return value.tolist()
            if isinstance(value, _np.generic):
                return value.item()
        except Exception:  # pragma: no cover
            pass
        return repr(value)


__all__ = ["CodeExecutor"]
