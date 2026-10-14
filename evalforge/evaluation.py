"""Strict two-stage faithfulness; extraction failures are never counted as passes."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str
    quote: str = Field(min_length=1)


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str
    label: Literal["supported", "unsupported", "contradicted"]
    evidence: list[Evidence]
    reason: str = Field(min_length=1)


class ClaimsOutput(BaseModel):
    model_config = ConfigDict(strict=True)
    claims: list[Claim]


class VerdictsOutput(BaseModel):
    model_config = ConfigDict(strict=True)
    verdicts: list[Verdict]


async def evaluate_answer(judge, answer, contexts):
    claims = []
    try:
        raw = await judge.complete("claims", {"answer": answer})
        claims = ClaimsOutput.model_validate(raw).claims
        if not claims:
            return {"status": "no_claims", "score": None, "claims": [], "verdicts": [], "error": None}
        if len({c.id for c in claims}) != len(claims):
            raise ValueError("声明 ID 重复")
        raw = await judge.complete("verify", {"claims": [c.model_dump() for c in claims], "contexts": contexts})
        verdicts = VerdictsOutput.model_validate(raw).verdicts
        if len(verdicts) != len(claims) or {v.claim_id for v in verdicts} != {c.id for c in claims}:
            raise ValueError("裁判必须为每个声明恰好返回一个 verdict")
        context_map = {c["id"]: c["text"] for c in contexts}
        if len(context_map) != len(contexts):
            raise ValueError("检索片段 ID 重复")
        for verdict in verdicts:
            if verdict.label in ("supported", "contradicted") and not verdict.evidence:
                raise ValueError("支持/矛盾判定必须包含原文证据")
            for evidence in verdict.evidence:
                if evidence.chunk_id not in context_map or evidence.quote not in context_map[evidence.chunk_id]:
                    raise ValueError("裁判引用不是上下文中的原文")
        return {
            "status": "ok", "score": sum(v.label == "supported" for v in verdicts) / len(claims),
            "claims": [c.model_dump() for c in claims], "verdicts": [v.model_dump() for v in verdicts], "error": None,
        }
    except (ValueError, KeyError, TypeError, ValidationError, RuntimeError) as exc:
        return {"status": "evaluation_error", "score": None, "claims": [c.model_dump() for c in claims],
                "verdicts": [], "error": str(exc)}
