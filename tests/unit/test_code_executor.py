"""Unit tests for the safe code-execution tooling (design/08 §code tools)."""

from __future__ import annotations

import pytest

from geometry_agent.config import CodeExecConfig
from geometry_agent.tools.code_executor import CodeExecutor
from geometry_agent.tools.geometry_prover import (
    complex_method,
    coordinate_method,
    projective_method,
)
from geometry_agent.tools.registry import get_tool_dispatchers, get_tool_schemas
from geometry_agent.tools.templates import get_template


# --------------------------------------------------------------------------- #
# 1. Simple arithmetic.
# --------------------------------------------------------------------------- #
def test_execute_simple_arithmetic():
    exe = CodeExecutor(CodeExecConfig())
    res = exe.execute("print(3+4)")
    assert res.success
    assert "7" in res.output


# --------------------------------------------------------------------------- #
# 2. SymPy equation solving.
# --------------------------------------------------------------------------- #
def test_execute_sympy_solve_quadratic():
    exe = CodeExecutor(CodeExecConfig())
    code = "import sympy as sp\nx = sp.symbols('x')\nprint(sp.solve(x**2-9, x))"
    res = exe.execute(code)
    assert res.success
    assert "3" in res.output
    assert "-3" in res.output


def test_execute_sympy_solve_quadratic_alt():
    exe = CodeExecutor(CodeExecConfig())
    code = "import sympy as sp; x=sp.symbols('x'); print(sp.solve(x**2-4,x))"
    res = exe.execute(code)
    assert res.success
    assert "2" in res.output


# --------------------------------------------------------------------------- #
# 3. Dangerous import is blocked.
# --------------------------------------------------------------------------- #
def test_execute_blocks_os_import():
    exe = CodeExecutor(CodeExecConfig())
    res = exe.execute("import os; os.system('ls')")
    assert res.success is False
    assert "import" in res.error.lower() or "blocked" in res.error.lower()
    # Make sure no directory listing leaked through.
    assert "pyproject.toml" not in res.output
    assert "configs" not in res.output


def test_execute_blocks_subprocess_import():
    exe = CodeExecutor(CodeExecConfig())
    res = exe.execute("import subprocess; subprocess.run(['echo', 'pwned'])")
    assert res.success is False


def test_execute_blocks_eval():
    exe = CodeExecutor(CodeExecConfig())
    res = exe.execute("eval('1+1')")
    assert res.success is False


def test_execute_blocks_open():
    exe = CodeExecutor(CodeExecConfig())
    res = exe.execute("open('/etc/passwd').read()")
    assert res.success is False


# --------------------------------------------------------------------------- #
# 4. Timeout (Unix only — signal.SIGALRM).
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not hasattr(__import__("signal"), "SIGALRM"),
                    reason="signal.SIGALRM unavailable on this platform")
def test_execute_timeout_infinite_loop():
    exe = CodeExecutor(CodeExecConfig(timeout_sec=0.5))
    res = exe.execute("while True:\n    pass")
    assert res.success is False
    assert "timeout" in res.error.lower()


# --------------------------------------------------------------------------- #
# 5. complex_method: collinearity check.
# --------------------------------------------------------------------------- #
def test_complex_method_collinear():
    res = complex_method({
        "points": {"A": [0, 0], "B": [1, 1], "C": [2, 2]},
        "relation": "collinear",
        "targets": ["A", "B", "C"],
    })
    assert res.success
    val = res.value
    assert isinstance(val, dict)
    assert val["verified"] is True


def test_complex_method_not_collinear():
    res = complex_method({
        "points": {"A": [0, 0], "B": [1, 0], "C": [0, 1]},
        "relation": "collinear",
        "targets": ["A", "B", "C"],
    })
    assert res.success
    assert res.value["verified"] is False


def test_complex_method_perpendicular():
    res = complex_method({
        "points": {"A": [0, 0], "B": [1, 1], "C": [1, 0], "D": [0, 1]},
        "relation": "perpendicular",
        "targets": ["A", "B", "C", "D"],
    })
    assert res.success
    assert res.value["verified"] is True


# --------------------------------------------------------------------------- #
# 6. coordinate_method: distance calculation.
# --------------------------------------------------------------------------- #
def test_coordinate_method_distance():
    res = coordinate_method({
        "points": {"A": [0, 0], "B": [3, 4]},
        "relation": "distance",
        "targets": ["A", "B"],
    })
    assert res.success
    val = res.value
    assert val["verified"] is True
    assert "5" in val["detail"]


def test_coordinate_method_distance_expected_mismatch():
    res = coordinate_method({
        "points": {"A": [0, 0], "B": [3, 4]},
        "relation": "distance",
        "targets": ["A", "B"],
        "expected": 6.0,
    })
    assert res.success
    assert res.value["verified"] is False


def test_coordinate_method_perpendicular():
    res = coordinate_method({
        "points": {"A": [0, 0], "B": [1, 1], "C": [1, 0], "D": [0, 1]},
        "relation": "perpendicular",
        "targets": ["A", "B", "C", "D"],
    })
    assert res.success
    assert res.value["verified"] is True


def test_projective_method_cross_ratio():
    res = projective_method({
        "points": {"A": [0, 0], "B": [1, 0], "C": [2, 0], "D": [3, 0]},
        "targets": ["A", "B", "C", "D"],
    })
    assert res.success
    assert "cross_ratio" in res.value


# --------------------------------------------------------------------------- #
# 7. Tool schemas include execute_code.
# --------------------------------------------------------------------------- #
def test_get_tool_schemas_includes_execute_code():
    schemas = get_tool_schemas()
    names = {s["function"]["name"] for s in schemas}
    assert "execute_code" in names
    assert {"verify", "solve", "search"} <= names
    assert {"complex_method", "coordinate_method", "projective_method"} <= names


def test_get_tool_dispatchers_returns_callables():
    dispatchers = get_tool_dispatchers({"verify": lambda **kw: {}})
    assert "execute_code" in dispatchers
    assert callable(dispatchers["execute_code"])
    assert "complex_method" in dispatchers
    assert "coordinate_method" in dispatchers
    assert "projective_method" in dispatchers
    # Existing tools passed through.
    assert "verify" in dispatchers


def test_dispatcher_execute_code_runs():
    dispatchers = get_tool_dispatchers()
    res = dispatchers["execute_code"](code="print(6*7)")
    assert res.success
    assert "42" in res.output


# --------------------------------------------------------------------------- #
# 8. get_template returns non-empty snippets.
# --------------------------------------------------------------------------- #
def test_get_template_solve_equation():
    t = get_template("解方程")
    assert t is not None
    assert "sympy" in t


def test_get_template_english_keyword():
    t = get_template("distance between A and B")
    assert t is not None
    assert "hypot" in t


def test_get_template_no_match():
    assert get_template("completely unrelated task") is None
    assert get_template("") is None


# --------------------------------------------------------------------------- #
# Extra: output truncation + execute_safe alias.
# --------------------------------------------------------------------------- #
def test_execute_truncates_long_output():
    exe = CodeExecutor(CodeExecConfig(max_output_chars=20))
    res = exe.execute("print('A' * 1000)")
    assert res.success
    assert len(res.output) <= 200  # truncation message included
    assert "truncated" in res.output


def test_execute_safe_alias_works():
    exe = CodeExecutor(CodeExecConfig())
    res = exe.execute_safe("print(2+2)")
    assert res.success
    assert "4" in res.output


def test_execute_captures_trailing_expression_value():
    exe = CodeExecutor(CodeExecConfig())
    res = exe.execute("1 + 2")
    assert res.success
    # value may be int 3 or string repr depending on displayhook path
    assert res.value in (3, "3")
