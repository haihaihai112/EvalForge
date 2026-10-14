"""Runnable HTTP adapter example: extractive lexical retrieval, not a production RAG agent."""
import re
import os

from fastapi import FastAPI
from pydantic import BaseModel, Field

from evalforge.config import ROOT
from evalforge.demo import SAMPLE_SOP
from evalforge.documents import import_document
from evalforge.storage import Database
from evalforge.tracing import Recorder

app = FastAPI(title="EvalForge example extractive Agent")
document = import_document("demo.md", SAMPLE_SOP.encode())
recorder = Recorder(Database(os.getenv("EVALFORGE_EXAMPLE_DB", str(ROOT / "data/example-agent.db"))))


class Question(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    document_id: str


@recorder.trace("示例词面检索", "retriever")
def retrieve(question, k):
    terms = set(re.findall(r"[\u4e00-\u9fff]{2}", question))
    ranked = sorted(document["chunks"], key=lambda c: sum(t in c["text"] for t in terms), reverse=True)
    return [{"id": c["id"], "text": c["text"]} for c in ranked[:k]]


@app.post("/answer")
@recorder.trace("示例抽取式 Agent", "agent")
async def answer(body: Question):
    if body.document_id != document["id"]:
        return {"answer": "现有 SOP 未提供该信息，应向制度负责人核实。", "contexts": [], "refused": True,
                "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0}
    contexts = retrieve(body.question, body.top_k)
    refused = any(word in body.question for word in ("私人", "手机号", "赔付金额"))
    return {"answer": "现有 SOP 未提供该信息，应向制度负责人核实。" if refused else "\n".join(c["text"] for c in contexts),
            "contexts": [] if refused else contexts, "refused": refused,
            "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0}
