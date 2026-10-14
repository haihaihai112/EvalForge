# EvalForge Implementation Plan

**Goal:** 交付可本地启动、可接真实模型和 HTTP Agent 的个人评测项目。
**Architecture:** FastAPI + SQLite + 无构建前端；裁判、Agent、存储、追踪、指标各自独立。
**Tech Stack:** Python 3.11+, FastAPI, HTTPX, Pydantic, Uvicorn, pypdf, pytest。
**Spec:** design.md

## Global constraints

仅本地代码；PowerShell 7；不依赖 DeepEval/Ragas/Phoenix；演示与真实测量明确区分；密钥不入库；未知指标为 null。

## 实施顺序

- [x] 核心评测：先写 supported/unsupported/contradicted、空声明、错 ID/引用、Recall/P95 测试，再实现 models.py、evaluation.py、metrics.py。
- [x] 追踪与持久化：先写 sync/async 父子链、并发隔离、异常重新抛出和敏感字段脱敏测试，再实现 storage.py、tracing.py。
- [x] 数据集与适配器：先写 50 题唯一性、来源合法性、文档格式、模型 HTTP 契约测试，再实现 documents.py、datasets.py、providers.py、agents.py。
- [x] API 与回归：先写导入→生成→运行→结果→导出集成测试及未配置 live 模式测试，再实现 service.py、app.py。
- [x] 本地界面：实现总览、测试集、工作台、审计页；浏览器验证导航、生成、运行、展开、导出、空态、窄屏和无控制台异常。
- [x] 交付：README、来源审计、启动脚本、完整测试；记录实际验证范围。

## 接口

`Database(path)`：`put(kind, payload)`、`get(kind,id)`、`list(kind)`、`save_span(payload)`、`spans(trace_id)`。
`Recorder(db)`：`@trace(name,kind)` 装饰 sync/async 函数，`annotate(**attrs)` 设置当前 span 属性。
`evaluate_answer(judge, answer, contexts)`：async，返回 claims/verdicts/score/status。
`generate_dataset(judge, document, count)`：async，返回带 evidence 和 review_status 的快照。
`execute_run(db,recorder,judge,agents,run_id)`：async，逐题更新 running/completed/failed 状态。

验证命令：`python -m pytest -q`；`python -m compileall -q evalforge`；`node --check evalforge/static/app.js`；浏览器实际操作验证。

