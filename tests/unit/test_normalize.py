"""Tests for geometry_agent.normalize — full-width input normalization."""

import pytest

from geometry_agent.normalize import normalize_problem_text


def test_fullwidth_digits_and_letters():
    assert normalize_problem_text("Ａ（１，２）Ｂ（３，４）") == "A(1,2)B(3,4)"
    assert normalize_problem_text("ｘ²＋ｙ²＝１") == "x²+y²=1"


def test_fullwidth_operators():
    assert normalize_problem_text("ｘ＋ｙ－ｚ×ｗ") == "x+y-z×w"  # × is a math symbol, kept
    assert normalize_problem_text("ＡＢ／ＣＤ＝１／２") == "AB/CD=1/2"
    assert normalize_problem_text("ｘ＞０，ｙ＜１，ｚ≥２") == "x>0,y<1,z≥2"
    assert normalize_problem_text("｛ｘ｜ｘ＞０｝") == "{x|x>0}"


def test_fullwidth_punctuation():
    assert normalize_problem_text("已知：△ＡＢＣ，求证：ＡＢ＝ＣＤ；") == "已知:△ABC,求证:AB=CD;"
    assert normalize_problem_text("［１，２］") == "[1,2]"
    assert normalize_problem_text("５０％") == "50%"


def test_fullwidth_space_and_minus():
    assert normalize_problem_text("Ａ　Ｂ") == "A B"
    assert normalize_problem_text("－３／４") == "-3/4"
    assert normalize_problem_text("−１") == "-1"  # U+2212


def test_chinese_punctuation_preserved():
    assert normalize_problem_text("求证。什么？加油！顿号、") == "求证。什么？加油！顿号、"


def test_math_symbols_untouched():
    assert normalize_problem_text("∠Ａ＝９０°，⌒ＡＢ，×，÷，²，³，⁻¹") == "∠A=90°,⌒AB,×,÷,²,³,⁻¹"


def test_empty_and_none_safe():
    assert normalize_problem_text("") == ""
    assert normalize_problem_text(None) is None


def test_idempotent():
    s = "Ａ（１，２）＝Ｂ（３，４）　－５"
    assert normalize_problem_text(normalize_problem_text(s)) == normalize_problem_text(s)
