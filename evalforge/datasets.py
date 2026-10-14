import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .evaluation import Evidence

from .demo import demo_cases

CATEGORIES = {"factual", "scenario", "multi_hop", "false_premise", "unanswerable"}


class Candidate(BaseModel):
    model_config = ConfigDict(strict=True)
    question: str = Field(min_length=1)
    category: Literal["factual", "scenario", "multi_hop", "false_premise", "unanswerable"]
    expected_answer: str = Field(min_length=1)
    expected_refusal: bool
    evidence: list[Evidence]


async def generate_dataset(judge, document, count=50):
    if not 1 <= count <= 50:
        raise ValueError("题目数量应为 1 至 50")
    if judge.mode == "demo":
        cases = demo_cases(document, count)
    else:
        cases, seen = [], set()
        context_map = {c["id"]: c["text"] for c in document["chunks"]}
        # Bounded attempts; never fabricate remaining items to fill the requested quota.
        for attempt in range(10):
            if len(cases) >= count:
                break
            result = await judge.complete("dataset", {"count": min(10, count - len(cases)), "chunks": document["chunks"],
                                                      "required_categories": sorted({"multi_hop", "false_premise", "unanswerable"} - {c["category"] for c in cases}) if count >= 8 else [],
                                                      "existing_questions": list(seen), "batch": attempt + 1})
            raw_cases = result.get("cases") if isinstance(result, dict) else None
            if not isinstance(raw_cases, list):
                continue
            for raw in raw_cases:
                try:
                    raw = Candidate.model_validate(raw).model_dump()
                except ValidationError:
                    continue
                question = str(raw.get("question", "")).strip()
                if not question or question in seen:
                    continue
                category = raw.get("category")
                evidence = raw.get("evidence", [])
                if category not in CATEGORIES or not raw.get("expected_answer") or not isinstance(raw.get("expected_refusal"), bool):
                    continue
                if (category == "unanswerable") != raw["expected_refusal"]:
                    continue
                if not raw["expected_refusal"] and not evidence:
                    continue
                if raw["expected_refusal"] and evidence:
                    continue
                if any(e.get("chunk_id") not in context_map or not e.get("quote") or e["quote"] not in context_map[e["chunk_id"]] for e in evidence):
                    continue
                ids = list(dict.fromkeys(e["chunk_id"] for e in evidence))
                if category == "multi_hop" and len(ids) < 2:
                    continue
                seen.add(question)
                cases.append({"id": f"case_{len(cases)+1:03}", "question": question, "category": category,
                              "expected_answer": str(raw["expected_answer"]), "expected_refusal": raw["expected_refusal"],
                              "expected_chunk_ids": ids, "evidence": evidence, "review_status": "candidate"})
                if len(cases) == count:
                    break
        if len(cases) != count:
            raise ValueError(f"模型仅生成 {len(cases)}/{count} 条有效题目，请降低数量或扩充 SOP。未保存不完整数据集。")
        missing = {"multi_hop", "false_premise", "unanswerable"} - {c["category"] for c in cases}
        if count >= 8 and missing:
            raise ValueError("生成集缺少多跳、错误前提或不可回答题，请重新生成。未保存类别不完整的数据集。")
    fingerprint = hashlib.sha256(json.dumps(cases, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {"name": document["name"].rsplit(".", 1)[0] + " · 测试集", "document_id": document["id"],
            "document_sha256": document["sha256"], "mode": judge.mode, "cases": cases,
            "fingerprint": fingerprint, "review_status": "candidate", "generation_usage": dict(judge.usage)}
