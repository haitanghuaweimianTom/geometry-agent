import json
from unittest.mock import MagicMock
from geometry_agent.verification import Step, Verdict, VerifyState
from geometry_agent.verification.llm_judge import LLMJudge


class FakeClient:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0
        self.last_messages = None
    def chat(self, messages, **kw):
        self.calls += 1
        self.last_messages = messages
        return {"choices": [{"message": {"role": "assistant", "content": self.reply}}]}


def _mk(stmt, pids=None): return Step(id="s", statement=stmt, premise_ids=pids or [], justification="")


def test_judge_returns_true_when_llm_says_valid():
    c = FakeClient(json.dumps({"verdict":"true","reason":"by AM-GM"}))
    j = LLMJudge(c)
    v = j.judge(_mk("a+b>=2*sqrt(a*b)"), [], ["simplify timeout"])
    assert v.verified == VerifyState.TRUE
    assert "AM-GM" in v.reason or "am" in v.reason.lower()
    assert c.calls == 1
    assert len(c.last_messages) == 2


def test_judge_returns_false_when_llm_says_invalid():
    c = FakeClient(json.dumps({"verdict":"false","reason":"counterexample a=1,b=2 fails"}))
    j = LLMJudge(c)
    v = j.judge(_mk("a+b>=2*sqrt(a*b)"), [], [])
    assert v.verified == VerifyState.FALSE


def test_judge_returns_uncertain_on_garbled_reply():
    c = FakeClient("i'm not sure about this")
    j = LLMJudge(c)
    v = j.judge(_mk("a+b>=2*sqrt(a*b)"), [], [])
    assert v.verified == VerifyState.UNCERTAIN


def test_judge_returns_uncertain_on_client_exception():
    class BoomClient:
        def chat(self, messages, **kw): raise RuntimeError("network down")
    j = LLMJudge(BoomClient())
    v = j.judge(_mk("1+1=2"), [], [])
    assert v.verified == VerifyState.UNCERTAIN
    assert "network down" in v.reason


def test_judge_includes_premises_in_prompt():
    c = FakeClient('{"verdict":"uncertain","reason":""}')
    j = LLMJudge(c)
    j.judge(_mk("x=5", ["p1"]), [Step(id="p1", statement="2*x=10", premise_ids=[], justification="solve")], [])
    user_msg = c.last_messages[1]["content"]
    assert "2*x=10" in user_msg
    assert "x=5" in user_msg
