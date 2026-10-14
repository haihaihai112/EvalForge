from fastapi.testclient import TestClient
from evalforge.app import create_app
import json
import httpx
import pytest


def test_complete_local_workflow(tmp_path):
    with TestClient(create_app(tmp_path / "api.db", seed=False)) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        from evalforge.demo import SAMPLE_SOP
        response = client.post("/api/documents?name=sop.md", content=SAMPLE_SOP.encode(), headers={"Content-Type": "text/plain"})
        assert response.status_code == 200
        document = response.json()
        dataset = client.post("/api/datasets", json={"document_id": document["id"], "count": 50, "mode": "demo"}).json()
        assert len(dataset["cases"]) == 50
        assert client.get(f'/api/datasets/{dataset["id"]}/export').json()["id"] == dataset["id"]
        # Candidate data must be reviewed explicitly before a regression.
        assert client.post("/api/runs", json={"dataset_id": dataset["id"], "mode": "demo"}).status_code == 409
        assert client.post(f'/api/datasets/{dataset["id"]}/approve').status_code == 200
        response = client.post("/api/runs", json={"dataset_id": dataset["id"], "mode": "demo"})
        assert response.status_code == 200
        run = client.get(f'/api/runs/{response.json()["id"]}').json()
        assert run["status"] == "completed"
        assert run["progress"] == 100
        assert len(run["results"]) == 100
        assert run["summaries"]["LogiGraph v2.0 · 演示"]["faithfulness"] > run["summaries"]["LogiGraph v1.0 · 演示"]["faithfulness"]
        trace_id = run["results"][0]["trace_id"]
        spans = client.get(f"/api/spans?trace_id={trace_id}").json()
        assert any(s["kind"] == "agent" for s in spans)
        assert any(s["kind"] == "judge" for s in spans)
        assert client.get("/").status_code == 200


def test_live_mode_without_configuration_is_explicit(tmp_path, monkeypatch):
    monkeypatch.delenv("EVALFORGE_API_KEY", raising=False)
    with TestClient(create_app(tmp_path / "live.db", seed=False)) as client:
        from evalforge.demo import SAMPLE_SOP
        doc = client.post("/api/documents?name=sop.md", content=SAMPLE_SOP.encode()).json()
        response = client.post("/api/datasets", json={"document_id": doc["id"], "count": 5, "mode": "live"})
        assert response.status_code == 400
        assert "EVALFORGE_API_KEY" in response.json()["detail"]


def test_invalid_count_and_missing_resources_are_handled(tmp_path):
    with TestClient(create_app(tmp_path / "validation.db", seed=False)) as client:
        assert client.post("/api/datasets", json={"document_id": "missing", "count": 0}).status_code == 422
        assert client.get("/api/runs/missing").status_code == 404
        assert client.post("/api/documents?name=bad.txt", content=b" ").status_code == 400


def test_live_protocol_full_run_does_not_send_golden_answers(tmp_path, monkeypatch):
    from evalforge.demo import SAMPLE_SOP
    from evalforge.providers import DemoJudge
    for key, value in {
        "EVALFORGE_API_BASE": "https://fixture.test/v1", "EVALFORGE_API_KEY": "fixture-key",
        "EVALFORGE_MODEL": "fixture-judge", "EVALFORGE_INPUT_PRICE": "2", "EVALFORGE_OUTPUT_PRICE": "4",
        "EVALFORGE_AGENT_1_URL": "https://fixture.test/agent/1", "EVALFORGE_AGENT_2_URL": "https://fixture.test/agent/2",
        "EVALFORGE_AGENT_1_NAME": "Fixture v1", "EVALFORGE_AGENT_2_NAME": "Fixture v2",
    }.items():
        monkeypatch.setenv(key, value)
    with TestClient(create_app(tmp_path / "protocol.db", seed=False)) as client:
        doc = client.post("/api/documents?name=sop.md", content=SAMPLE_SOP.encode()).json()
        ds = client.post("/api/datasets", json={"document_id": doc["id"], "count": 5}).json()
        client.post(f'/api/datasets/{ds["id"]}/approve')
        recorded_requests = []

        async def handler(request):
            body = json.loads(request.content)
            if request.url.path.startswith("/agent/"):
                assert set(body) == {"question", "top_k", "document_id"}
                recorded_requests.append(body)
                chunk = doc["chunks"][0]
                return httpx.Response(200, json={"answer": chunk["text"], "contexts": [{"id": chunk["id"], "text": chunk["text"]}], "refused": False, "cost_usd": .0001})
            assert request.headers["Authorization"] == "Bearer fixture-key"
            payload = json.loads(body["messages"][1]["content"])
            result = await DemoJudge().complete("claims" if "answer" in payload else "verify", payload)
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result, ensure_ascii=False)}}],
                                            "usage": {"prompt_tokens": 100, "completion_tokens": 20}})

        original_client = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
        response = client.post("/api/runs", json={"dataset_id": ds["id"], "mode": "live"})
        assert response.status_code == 200
        run = client.get('/api/runs/' + response.json()["id"]).json()
        assert run["status"] == "completed"
        assert len(recorded_requests) == 10
        assert run["judge_prices_per_million"] == {"input": 2.0, "output": 4.0}
        for summary in run["summaries"].values():
            assert summary["error_rate"] == 0
            assert summary["evaluation_error_count"] == 0
            assert summary["faithfulness"] == 1
            assert summary["cost_usd"] == pytest.approx(.0001)
            assert summary["judge_cost_usd"] == pytest.approx(.0028)
