import asyncio
import os
import time

from .agents import DemoAgent, HttpAgent
from .config import model_config
from .evaluation import evaluate_answer
from .metrics import recall_at_k, summarize
from .providers import DemoJudge, ModelJudge
from .storage import now
from .tracing import redact


def make_judge(mode, recorder):
    return DemoJudge(recorder) if mode == "demo" else ModelJudge(**model_config(), recorder=recorder)


def make_agents(mode, recorder):
    if mode == "demo":
        return [DemoAgent(1, recorder), DemoAgent(2, recorder)]
    agents = []
    for i in (1, 2):
        url = os.getenv(f"EVALFORGE_AGENT_{i}_URL", "")
        if not url:
            raise ValueError(f"请配置 EVALFORGE_AGENT_{i}_URL")
        agents.append(HttpAgent(os.getenv(f"EVALFORGE_AGENT_{i}_NAME", f"Agent v{i}"), url, recorder, os.getenv(f"EVALFORGE_AGENT_{i}_TOKEN", "")))
    if agents[0].name == agents[1].name:
        raise ValueError("两个 Agent 版本名称必须不同")
    return agents


async def execute_run(db, recorder, run_id):
    run = db.get("runs", run_id)
    run.update(status="running", started_at=now())
    db.put("runs", run)
    try:
        agents = make_agents(run["mode"], recorder)
        document = run["document_snapshot"]
        cases = run["dataset_snapshot"]["cases"]

        @recorder.trace("单题评测", "evaluation")
        async def evaluate_case(case, agent):
            recorder.annotate(run_id=run_id, case_id=case["id"], version=agent.name, mode=run["mode"])
            ids = recorder.current_ids()
            result = {"case_id": case["id"], "question": case["question"], "category": case["category"],
                      "version": agent.name, "expected_answer": case["expected_answer"],
                      "expected_refusal": case["expected_refusal"], **ids}
            started = time.perf_counter()
            try:
                output = await agent.respond(case, document, run["top_k"])
                latency = (time.perf_counter() - started) * 1000
                judge = make_judge(run["mode"], recorder)
                evaluation = await evaluate_answer(judge, output["answer"], output["contexts"])
                known = {c["id"] for c in document["chunks"]}
                retrieved = [c["id"] for c in output["contexts"]]
                # Unknown external chunk namespaces require a mapping, rather than a misleading zero recall.
                valid_ids = retrieved if set(retrieved) <= known else None
                result.update(status="ok", answer=output["answer"], contexts=output["contexts"],
                              refused=output["refused"], latency_ms=round(latency, 4),
                              cost_usd=output["cost_usd"], prompt_tokens=output["prompt_tokens"],
                              completion_tokens=output["completion_tokens"], evaluation=evaluation,
                              judge_cost_usd=judge.usage["cost_usd"],
                              recall=recall_at_k(case["expected_chunk_ids"], valid_ids, run["top_k"]),
                              error=None)
            except Exception as exc:
                result.update(status="agent_error", answer="", contexts=[], latency_ms=round((time.perf_counter() - started) * 1000, 4),
                              cost_usd=None, judge_cost_usd=None, evaluation={"score": None, "status": "not_evaluated", "claims": [], "verdicts": []},
                              recall=None, error=redact(str(exc)))
            return result

        for case in cases:
            for agent in agents:
                result = await evaluate_case(case, agent)
                run["results"].append(result)
                run["progress"] = round(len(run["results"]) / (len(cases) * len(agents)) * 100)
                run["summaries"] = {a.name: summarize([r for r in run["results"] if r["version"] == a.name]) for a in agents}
                db.put("runs", run)
                await asyncio.sleep(0)
        run.update(status="completed", ended_at=now(), progress=100)
    except asyncio.CancelledError:
        run.update(status="interrupted", ended_at=now(), error="服务停止，运行已中断，请新建一次运行。")
        raise
    except Exception as exc:
        run.update(status="failed", ended_at=now(), error=redact(str(exc)))
    finally:
        db.put("runs", run)
