import json
from unittest.mock import MagicMock

from geometry_agent.types import VerifyState
from geometry_agent.verification import Step
from geometry_agent.verification.lean_client import LeanStepVerifier


def _mk(stmt="1+1=2"):
    return Step(id="s", statement=stmt, premise_ids=[], justification="")


def _fake_response(status, body):
    r = MagicMock()
    r.status_code = status
    r.text = json.dumps(body)
    r.json = lambda body=body: body
    return r


def test_lean_verify_true(monkeypatch):
    import requests
    v = LeanStepVerifier("http://x:9407", timeout_s=2)
    fake_post = MagicMock(return_value=_fake_response(200, {"verified": True, "output": "ok"}))
    monkeypatch.setattr(requests, "post", fake_post)
    r = v.verify(_mk(), [])
    assert r.verified == VerifyState.TRUE
    assert "ok" in r.evidence


def test_lean_verify_false(monkeypatch):
    import requests
    v = LeanStepVerifier("http://x:9407")
    fake_post = MagicMock(return_value=_fake_response(
        200, {"verified": False, "output": "error: type mismatch"}))
    monkeypatch.setattr(requests, "post", fake_post)
    r = v.verify(_mk("1+1=3"), [])
    assert r.verified == VerifyState.FALSE


def test_lean_unreachable_returns_uncertain(monkeypatch):
    import requests
    v = LeanStepVerifier("http://x:9407")

    def boom(*a, **kw):
        raise requests.ConnectionError("refused")
    monkeypatch.setattr(requests, "post", boom)
    r = v.verify(_mk(), [])
    assert r.verified == VerifyState.UNCERTAIN
    assert "unreachable" in r.reason


def test_lean_client_sends_correct_endpoint(monkeypatch):
    import requests
    v = LeanStepVerifier("http://host:9999")
    captured = {}

    def fake_post(url, **kw):
        captured["url"] = url
        return _fake_response(200, {"verified": True, "output": ""})
    monkeypatch.setattr(requests, "post", fake_post)
    v.verify(_mk(), [])
    assert captured["url"] == "http://host:9999/verify"
