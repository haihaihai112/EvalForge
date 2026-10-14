"""Explicit denominators and missing values. Never average unavailable data as zero."""
import math
from statistics import mean


def recall_at_k(expected, retrieved, k=5):
    if not expected or retrieved is None:
        return None
    return len(set(expected) & set(retrieved[:k])) / len(set(expected))


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def average(values):
    values = [v for v in values if v is not None]
    return mean(values) if values else None


def summarize(results):
    successes = [r for r in results if r["status"] == "ok"]
    scored = [r for r in successes if r.get("evaluation", {}).get("score") is not None]
    costs = [r.get("cost_usd") for r in results]
    return {
        "count": len(results), "success_count": len(successes),
        "error_rate": 1 - len(successes) / len(results) if results else None,
        "faithfulness": average([r["evaluation"]["score"] for r in scored]),
        "scored_count": len(scored),
        "evaluation_error_count": sum(r.get("evaluation", {}).get("status") == "evaluation_error" for r in successes),
        "no_claims_count": sum(r.get("evaluation", {}).get("status") == "no_claims" for r in successes),
        "recall": average([r.get("recall") for r in successes]),
        "recall_count": sum(r.get("recall") is not None for r in successes),
        "p95_ms": percentile([r["latency_ms"] for r in successes], .95),
        "cost_usd": mean(costs) if costs and all(c is not None for c in costs) else None,
        "judge_cost_usd": sum(r.get("judge_cost_usd") or 0 for r in results) if results and all(r.get("judge_cost_usd") is not None for r in results) else None,
        "refusal_accuracy": average([int(r.get("refused", False) == r["expected_refusal"]) for r in successes if "expected_refusal" in r]),
    }
