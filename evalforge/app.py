import hashlib
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import ROOT, load_env, model_config, public_config
from .datasets import generate_dataset
from .demo import SAMPLE_SOP
from .documents import MAX_BYTES, import_document
from .service import execute_run, make_agents, make_judge
from .storage import Database
from .tracing import Recorder
from .providers import PROMPTS


class DatasetRequest(BaseModel):
    document_id: str
    count: int = Field(default=50, ge=1, le=50)
    mode: Literal["demo", "live"] = "demo"


class RunRequest(BaseModel):
    dataset_id: str
    mode: Literal["demo", "live"] = "demo"
    top_k: int = Field(default=5, ge=1, le=20)
    name: str = Field(default="版本回归", min_length=1, max_length=100)


def compact_run(run):
    return {k: v for k, v in run.items() if k not in ("results", "dataset_snapshot", "document_snapshot")}


def create_app(db_path=None, seed=True):
    load_env()
    db = Database(db_path or os.getenv("EVALFORGE_DB", str(ROOT / "data/evalforge.db")))
    recorder = Recorder(db)

    def require(kind, record_id):
        value = db.get(kind, record_id)
        if value is None:
            raise HTTPException(404, "记录不存在")
        return value

    def new_run(dataset, mode, top_k=5, name="版本回归"):
        agents = make_agents(mode, recorder)
        return db.put("runs", {"name": name, "dataset_id": dataset["id"], "dataset_name": dataset["name"],
                               "dataset_fingerprint": dataset["fingerprint"], "dataset_snapshot": dataset,
                               "document_snapshot": require("documents", dataset["document_id"]),
                               "mode": mode, "top_k": top_k, "versions": [a.name for a in agents],
                               "judge_model": "demo-string-v1" if mode == "demo" else model_config()["model"],
                               "judge_prompt_sha256": hashlib.sha256(json.dumps(PROMPTS, sort_keys=True).encode()).hexdigest(),
                               "judge_prices_per_million": {"input": model_config()["input_price"], "output": model_config()["output_price"]} if mode == "live" else None,
                               "metric_version": "faithfulness-strict-v1", "status": "queued", "progress": 0,
                               "results": [], "summaries": {}, "error": None})

    @asynccontextmanager
    async def lifespan(app):
        for run in db.list("runs"):
            if run["status"] in ("queued", "running"):
                run.update(status="interrupted", error="上次服务在运行结束前停止，请重新运行。")
                db.put("runs", run)
        if seed and not db.list("datasets"):
            document = db.put("documents", import_document("北辰物流演示SOP.md", SAMPLE_SOP.encode()))
            dataset = await generate_dataset(make_judge("demo", recorder), document, 50)
            dataset.update(name="仓配 SOP · 50 题演示集", review_status="approved")
            for case in dataset["cases"]:
                case["review_status"] = "approved"
            dataset = db.put("datasets", dataset)
            run = new_run(dataset, "demo", name="LogiGraph 双版本演示回归")
            await execute_run(db, recorder, run["id"])
        yield

    app = FastAPI(title="EvalForge", version="0.1.0", lifespan=lifespan)
    app.state.db, app.state.recorder = db, recorder

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(RuntimeError)
    async def model_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=502)

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/config")
    async def config():
        return public_config()

    @app.get("/api/overview")
    async def overview():
        runs = db.list("runs")
        return {"documents": len(db.list("documents")), "datasets": len(db.list("datasets")),
                "runs": len(runs), "recent_runs": [compact_run(r) for r in runs[:8]],
                "latest": next((compact_run(r) for r in runs if r["status"] == "completed"), None)}

    @app.get("/api/documents")
    async def documents():
        return [{k: v for k, v in doc.items() if k not in ("text", "chunks")} | {"chunk_count": len(doc["chunks"])} for doc in db.list("documents")]

    @app.get("/api/documents/{document_id}")
    async def document(document_id: str):
        return require("documents", document_id)

    @app.post("/api/documents")
    async def upload(request: Request, name: str = "sop.txt"):
        content = bytearray()
        async for part in request.stream():
            content.extend(part)
            if len(content) > MAX_BYTES:
                raise HTTPException(413, "文档不能超过 8 MB")
        return db.put("documents", import_document(name, bytes(content)))

    @app.get("/api/sample-sop")
    async def sample():
        return {"name": "北辰物流演示SOP.md", "text": SAMPLE_SOP}

    @app.get("/api/datasets")
    async def datasets():
        return [{k: v for k, v in d.items() if k != "cases"} | {"case_count": len(d["cases"])} for d in db.list("datasets")]

    @app.post("/api/datasets")
    async def synthesize(body: DatasetRequest):
        doc = require("documents", body.document_id)
        judge = make_judge(body.mode, recorder)
        return db.put("datasets", await generate_dataset(judge, doc, body.count))

    @app.get("/api/datasets/{dataset_id}")
    async def dataset(dataset_id: str):
        return require("datasets", dataset_id)

    @app.post("/api/datasets/{dataset_id}/approve")
    async def approve(dataset_id: str):
        value = require("datasets", dataset_id)
        value["review_status"] = "approved"
        for case in value["cases"]:
            case["review_status"] = "approved"
        # Content fingerprint excludes review metadata; answers/evidence stay immutable.
        return db.put("datasets", value)

    @app.get("/api/datasets/{dataset_id}/export")
    async def export_dataset(dataset_id: str):
        return JSONResponse(require("datasets", dataset_id), headers={"Content-Disposition": f'attachment; filename="dataset-{dataset_id}.json"'})

    @app.get("/api/runs")
    async def runs():
        return [compact_run(r) for r in db.list("runs")]

    @app.post("/api/runs")
    async def start_run(body: RunRequest, background: BackgroundTasks):
        dataset = require("datasets", body.dataset_id)
        if dataset["review_status"] != "approved":
            raise HTTPException(409, "请先审阅并确认候选测试集")
        if any(r["status"] in ("queued", "running") for r in db.list("runs")):
            raise HTTPException(409, "已有运行正在执行，请等待完成")
        if body.mode == "live":
            model_config()
        run = new_run(dataset, body.mode, body.top_k, body.name)
        background.add_task(execute_run, db, recorder, run["id"])
        return compact_run(run)

    @app.get("/api/runs/{run_id}")
    async def run(run_id: str):
        return require("runs", run_id)

    @app.get("/api/runs/{run_id}/export")
    async def export_run(run_id: str):
        return JSONResponse(require("runs", run_id), headers={"Content-Disposition": f'attachment; filename="run-{run_id}.json"'})

    @app.get("/api/spans")
    async def spans(trace_id: str | None = None):
        return db.spans(trace_id)

    @app.get("/")
    async def index():
        return FileResponse(Path(__file__).parent / "static/index.html")

    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    return app
