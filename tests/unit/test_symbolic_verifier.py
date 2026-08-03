from geometry_agent.verification import Step
from geometry_agent.types import VerifyState
from geometry_agent.verification.symbolic import SymbolicStepVerifier
from geometry_agent.verification.step_parser import parse_claim, parse_expr


def _mk(stmt, pids=None):
    return Step(id="s", statement=stmt, premise_ids=pids or [], justification="")
def _premise(stmt, pid):
    return Step(id=pid, statement=stmt, premise_ids=[], justification="")


class TestStepParser:
    def test_equality_basic(self):
        r = parse_claim("a = b")
        assert r is not None
        lhs, rel, rhs = r
        assert rel.__name__ == "Equality"  # sp.Eq

    def test_chinese_parentheses_and_punct(self):
        r = parse_claim("（a+b）^2 = a^2 + 2ab + b^2")
        assert r is not None

    def test_sqrt(self):
        r = parse_claim("sqrt(a^2+b^2) = c")
        assert r is not None

    def test_inequality_ge(self):
        r = parse_claim("a+b >= 2*sqrt(a*b)")
        assert r is not None

    def test_no_relation_returns_none(self):
        assert parse_claim("just some text") is None

    def test_parse_expr(self):
        e = parse_expr("2*sqrt(2)")
        assert e is not None


class TestSymbolicVerifier:
    def test_algebraic_identity_true(self):
        v = SymbolicStepVerifier()
        r = v.verify(_mk("(a+b)^2 = a^2 + 2*a*b + b^2"), [])
        assert r.verified == VerifyState.TRUE

    def test_algebraic_identity_false(self):
        v = SymbolicStepVerifier()
        r = v.verify(_mk("(a+b)^2 = a^2 + b^2"), [])
        assert r.verified == VerifyState.FALSE

    def test_trig_identity_sin2x(self):
        v = SymbolicStepVerifier(timeout_ms=500)
        r = v.verify(_mk("sin(2*x) = 2*sin(x)*cos(x)"), [])
        assert r.verified in (VerifyState.TRUE, VerifyState.UNCERTAIN)

    def test_equality_from_premises(self):
        v = SymbolicStepVerifier()
        r = v.verify(
            _mk("x = 5", ["p1"]),
            [_premise("2*x = 10", "p1")],
        )
        assert r.verified == VerifyState.TRUE

    def test_inequality_true_simple(self):
        v = SymbolicStepVerifier(timeout_ms=500)
        r = v.verify(_mk("x^2 >= 0"), [])
        assert r.verified in (VerifyState.TRUE, VerifyState.UNCERTAIN)

    def test_unparseable_returns_uncertain(self):
        v = SymbolicStepVerifier()
        r = v.verify(_mk("三角形ABC相似于DEF", []), [])
        assert r.verified == VerifyState.UNCERTAIN

    def test_timeout_returns_uncertain(self):
        v = SymbolicStepVerifier(timeout_ms=10)
        r = v.verify(_mk("x^100 + x^99 = x^99*(x+1)"), [])
        assert r.verified in (VerifyState.TRUE, VerifyState.UNCERTAIN)
