import asyncio
import pytest

from evalforge.evaluation import evaluate_answer
from evalforge.metrics import recall_at_k, percentile, summarize
from evalforge.storage import Database
from evalforge.tracing import Recorder


class Judge:
    def __init__(self, verdicts=None, claims=None):
        self.verdicts = verdicts
        self.claims = claims if claims is not None else ["必须登记", "免费赔偿", "24 小时"]

    async def complete(self, task, payload):
        if task == "claims":
            return {"claims": [{"id": f"c{i+1}", "text": t} for i, t in enumerate(self.claims)]}
        return {"verdicts": self.verdicts or [
            {"claim_id": "c1", "label": "supported", "evidence": [{"chunk_id": "s1", "quote": "必须登记"}], "reason": "原文支持"},
            {"claim_id": "c2", "label": "unsupported", "evidence": [], "reason": "未规定免费赔偿"},
            {"claim_id": "c3", "label": "contradicted", "evidence": [{"chunk_id": "s1", "quote": "48 小时"}], "reason": "时间不同"},
        ]}


def test_only_evidence_supported_claims_score():
    result = asyncio.run(evaluate_answer(Judge(), "answer", [{"id": "s1", "text": "必须登记，48 小时。"}]))
    assert result["score"] == pytest.approx(1 / 3)
    assert result["status"] == "ok"


def test_empty_claims_do_not_pass():
    result = asyncio.run(evaluate_answer(Judge(claims=[]), "不知道", []))
    assert result["score"] is None
    assert result["status"] == "no_claims"


@pytest.mark.parametrize("malformed", [{}, "", None])
def test_wrong_claim_collection_is_judge_error(malformed):
    class BadJudge:
        async def complete(self, task, payload):
            return {"claims": malformed}
    result = asyncio.run(evaluate_answer(BadJudge(), "answer", []))
    assert result["status"] == "evaluation_error"
    assert result["score"] is None


@pytest.mark.parametrize("verdicts", [
    [{"claim_id": "c1", "label": "supported", "evidence": [{"chunk_id": "s1", "quote": "伪造引用"}], "reason": "支持"}],
    [{"claim_id": "wrong", "label": "unsupported", "evidence": [], "reason": "未知"}],
    [{"claim_id": "c1", "label": "supported", "evidence": [], "reason": "支持"}],
])
def test_bad_judge_output_is_error_not_a_good_score(verdicts):
    result = asyncio.run(evaluate_answer(Judge(verdicts=verdicts, claims=["必须登记"]), "answer", [{"id": "s1", "text": "必须登记"}]))
    assert result["status"] == "evaluation_error"
    assert result["score"] is None


def test_metrics_require_real_retrieval_ids_and_keep_unknown_cost():
    assert recall_at_k(["a", "b"], ["a", "a", "c"], 2) == .5
    assert recall_at_k([], ["a"], 3) is None
    assert recall_at_k(["a"], None, 3) is None
    assert percentile([1, 2, 3, 4, 5], .95) == pytest.approx(4.8)
    summary = summarize([{"status": "ok", "latency_ms": 5, "cost_usd": None, "evaluation": {"score": 1}, "recall": .5}])
    assert summary["cost_usd"] is None
    assert summary["faithfulness"] == 1


def test_tracing_records_nested_sync_failure_and_redacts(tmp_path):
    db = Database(tmp_path / "test.db")
    recorder = Recorder(db)

    @recorder.trace("child", "tool")
    def child(api_key):
        raise ValueError("test failure")

    @recorder.trace("parent", "agent")
    def parent():
        child(api_key="do-not-store")

    with pytest.raises(ValueError, match="test failure"):
        parent()
    spans = db.spans()
    assert len(spans) == 2
    root = next(s for s in spans if s["parent_span_id"] is None)
    leaf = next(s for s in spans if s["parent_span_id"] is not None)
    assert leaf["parent_span_id"] == root["span_id"]
    assert leaf["status"] == root["status"] == "error"
    assert "do-not-store" not in str(spans)


def test_concurrent_async_traces_never_mix_parents(tmp_path):
    db = Database(tmp_path / "async.db")
    recorder = Recorder(db)

    @recorder.trace("leaf", "llm")
    async def leaf(value):
        await asyncio.sleep(.001)
        return value

    @recorder.trace("root", "agent")
    async def root(value):
        return await leaf(value)

    async def run():
        return await asyncio.gather(root("one"), root("two"))

    assert asyncio.run(run()) == ["one", "two"]
    spans = db.spans()
    roots = [s for s in spans if s["parent_span_id"] is None]
    assert len({s["trace_id"] for s in roots}) == 2
    for parent in roots:
        children = [s for s in spans if s["parent_span_id"] == parent["span_id"]]
        assert len(children) == 1
        assert children[0]["trace_id"] == parent["trace_id"]
