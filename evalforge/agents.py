import httpx
from pydantic import BaseModel, Field, ConfigDict


class Context(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class AgentOutput(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    answer: str = Field(min_length=1)
    contexts: list[Context]
    refused: bool = False
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)


class DemoAgent:
    def __init__(self, version, recorder):
        self.version = version
        self.name = f"LogiGraph v{version}.0 · 演示"
        self.recorder = recorder
        self.respond = recorder.trace(self.name, "agent")(self.respond)
        self.retrieve = recorder.trace("检索片段（演示 fixture）", "retriever")(self.retrieve)
        self.generate = recorder.trace("回答生成（演示 fixture）", "llm")(self.generate)

    async def retrieve(self, case, document, k):
        ids = case["expected_chunk_ids"]
        if self.version == 1 and case["category"] == "multi_hop":
            ids = ids[:1]
        return [{"id": c["id"], "text": c["text"]} for c in document["chunks"] if c["id"] in ids][:k]

    async def generate(self, case, contexts):
        self.recorder.annotate(usage={"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0}, mode="demo")
        index = int(case["id"].rsplit("_", 1)[-1])
        if case["expected_refusal"]:
            if self.version == 1 and index % 10 == 0:
                return "负责人的私人手机号为 13800138000。", False
            return "现有 SOP 未提供该信息，应向制度负责人核实。", True
        answer = case["expected_answer"]
        # Known fault fixtures: v1 invents policy more often. They do not emulate vector/GraphRAG algorithms.
        if index % (4 if self.version == 1 else 19) == 0:
            answer += "\n所有异常均可自动赔付 500 元。"
        return answer, False

    async def respond(self, case, document, k):
        contexts = await self.retrieve(case, document, k)
        answer, refused = await self.generate(case, contexts)
        self.recorder.annotate(mode="demo", usage_source="fixture_no_billing")
        return {"answer": answer, "contexts": contexts, "refused": refused,
                "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}


class HttpAgent:
    def __init__(self, name, url, recorder, token=""):
        if not url.startswith(("http://", "https://")):
            raise ValueError("Agent 地址必须为 HTTP(S) URL")
        self.name, self.url, self.token, self.recorder = name, url, token, recorder
        self.respond = recorder.trace(name, "agent")(self.respond)

    async def respond(self, case, document, k):
        headers = {"Authorization": "Bearer " + self.token} if self.token else {}
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(self.url, json={"question": case["question"], "top_k": k,
                                                           "document_id": document["id"]}, headers=headers)
                response.raise_for_status()
                output = AgentOutput.model_validate(response.json()).model_dump()
            if len({c["id"] for c in output["contexts"]}) != len(output["contexts"]):
                raise ValueError("Agent 返回重复的 context ID")
            self.recorder.annotate(usage={k: output[k] for k in ("prompt_tokens", "completion_tokens", "cost_usd")})
            return output
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise RuntimeError(f"Agent 调用失败：{type(exc).__name__}；请检查服务与响应协议") from exc
