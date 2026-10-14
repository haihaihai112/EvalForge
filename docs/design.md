# EvalForge 本地项目设计

目标：从物流 SOP 构建可审阅测试集，在同一数据集上比较多个 Agent 版本，定位不受证据支持的回答和执行故障。仅本地交付，不发布、不调用 DeepEval/Ragas 黑盒评估库。

## 架构

- FastAPI 提供 JSON API 并托管原生 HTML/CSS/JavaScript 页面；Python 3.11+，无需 Node 构建。
- SQLite 保存文档、数据集、运行快照以及独立 spans；WAL + synchronous=NORMAL + busy_timeout。
- Judge 接口隔离演示裁判与真实模型；真实模型使用可配置 HTTP chat/completions JSON 协议。
- Agent 接口隔离确定性演示 Agent 与用户配置的两个 HTTP Agent。真实运行必须明确配置模型与 Agent 地址。
- claims 拆解 → retrieval context 原文核验 → 严格聚合；裁判错误与无声明不冒充满分。
- ContextVar + sync/async 装饰器维护 trace_id、span_id、parent_span_id；finally 路径记录异常并重新抛出。

## 页面与数据流

总览展示最近运行、版本雷达和逐指标原始值。测试集页面上传 TXT/MD/PDF/DOCX 并生成最多 50 条候选题。工作台提交后台运行并轮询进度，展开逐题声明和证据。审计页查看实际持久化的父子 Span、Prompt、工具参数和用量。

离线演示提供内置虚构 SOP 与 50 个模板测试题，刻意在两个演示 Agent 中注入不同错误，所有入口标注演示，不声称真实 GraphRAG 性能。真实模型生成的数据集先以 candidate 状态保存，可人工确认。测试数据不得自动进入训练集。

## 评测规则

Faithfulness = supported / claims；unsupported 和 contradicted 均不计分。每个 supported verdict 必须给出上下文中的原文引用和 chunk_id。返回条数/ID、引用、JSON 不合法时本题 evaluation_error；无声明 score=null，另看拒答表现。

Recall@k 按 golden evidence chunk ID 与实际 top-k chunk ID 的交集计算；不可回答题不纳入 recall 分母。没有可靠 chunk ID 则 null。P95 使用成功 Agent 根调用实测耗时，另报失败率；裁判耗时与成本单列。未知 token/cost 为 null；按实际 usage 和用户配置价格估算美元成本，父子 span 不重复求和。

同一运行固定数据集快照、版本列表、k、judge 模式及版本。雷达固定阈值归一化、低延迟/低成本方向取反，缺失指标不伪装成 0。表格为解释指标的权威视图。

## 视觉

以审计工作台为核心：冷灰 #F3F6FA、白 #FFFFFF、深蓝 #172942、青蓝 #087E8B、琥珀 #B77918、红 #BF4255。Segoe UI/微软雅黑用于中文，等宽字体仅用于 ID 与代码。左侧导航、宽幅运行表格、右侧证据展开；雷达为唯一突出图形。键盘焦点、空态、加载态、错误态与窄屏布局均需检查。

## 验收

离线启动即有可操作的演示；导入文档和导出数据集可用；50 题后台回归、逐声明证据与链路可查看；跨异步任务父链不串线、异常不吞掉；未配置真实模式返回明确错误；真实模型契约用本地 HTTP fixture 验证，不声称已做在线模型测评。
