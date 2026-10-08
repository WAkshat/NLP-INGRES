import sqlite3

from src.pipeline.agent import Pipeline, PlaceLinker


class FakeClient:
    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def generate(self, prompt="", system="", messages=None):
        self.seen.append(messages)
        return {"text": self.replies.pop(0), "latency_s": 0.1, "prompt_tokens": 10, "output_tokens": 5}


class FakeLLM:
    def __init__(self, replies):
        self.client = FakeClient(replies)

    def prompt(self, question, hints=None, examples=None, places=""):
        return question


def make(replies, max_repairs=2):
    p = object.__new__(Pipeline)
    p.con = sqlite3.connect(":memory:")
    p.con.execute("CREATE TABLE t(x)")
    p.con.execute("INSERT INTO t VALUES (1)")
    p.cfg = {"max_repairs": max_repairs, "k_cols": 5, "k_shots": 3}
    p.llm, p.linker, p.places, p.TQ = FakeLLM(replies), None, None, None
    p.enc = type("E", (), {"encode": lambda self, xs, **k: [[0.0]]})()
    return p


def test_repair_after_error_then_success():
    p = make(["```sql\nSELECT y FROM t\n```", "```sql\nSELECT x FROM t\n```"])
    o = p.sql("q")
    assert o["first_sql"] == "SELECT y FROM t" and o["sql"] == "SELECT x FROM t" and len(o["attempts"]) == 2
    assert "no such column" in p.llm.client.seen[1][-1]["content"]


def test_no_repair_when_first_attempt_works_and_stop_when_model_insists():
    assert len(make(["SELECT x FROM t"]).sql("q")["attempts"]) == 1
    o = make(["SELECT x FROM t WHERE x > 5", "SELECT x FROM t WHERE x > 5", "unused"]).sql("q")
    assert len(o["attempts"]) == 2           # empty result, model returned the same query -> stop


def test_render_places():
    s = PlaceLinker.render([{"mention": "लुधियाना", "level": "district", "db_name": "LUDHIANA", "district": "LUDHIANA",
                             "state": "PUNJAB", "score": 0.99}])
    assert "district 'LUDHIANA' in state 'PUNJAB'" in s
