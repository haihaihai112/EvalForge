# Phoenix 追踪与入库链路源码审计

研究对象：`Arize-ai/phoenix`。固定提交：`9793e30feae1949f7bf972613aaf4275dc0b1b0b`。本笔记来自本地 shallow sparse checkout 的静态源码阅读，未启动 Phoenix、未做吞吐或崩溃恢复测试。

标记口径：**Observed** 是固定提交里可直接核对的行为；**Inferred** 是由代码推导的后果；**Proposed** 是 EvalForge 的设计建议；**Unknown** 是本次没有验证的内容。

## 1. 实际所有权：配置、插桩、传输、存储是四层

**Observed**：`phoenix.otel` 的 `register()` 是配置入口，不是一个把任意 Python 函数自动拦截并直接写入 SQLite 的函数。

| 层次 | 固定源码证据 | 观察 |
|---|---|---|
| Provider 所有权 | [otel.py:10](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/packages/phoenix-otel/src/phoenix/otel/otel.py#L10)、[otel.py:200](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/packages/phoenix-otel/src/phoenix/otel/otel.py#L200) | Phoenix 的 `TracerProvider` 继承外部 `openinference.instrumentation.TracerProvider`。 |
| 注册 | [otel.py:65–77](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/packages/phoenix-otel/src/phoenix/otel/otel.py#L65-L77)、[146–197](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/packages/phoenix-otel/src/phoenix/otel/otel.py#L146-L197) | 合并 project resource；创建 provider；选择 batch 或 simple processor；可设置全局 provider；可自动插桩。默认 `batch=False`、`auto_instrument=False`。 |
| 自动插桩 | [otel.py:829–841](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/packages/phoenix-otel/src/phoenix/otel/otel.py#L829-L841) | 枚举 `openinference_instrumentor` entry points，加载已安装 instrumentor，调用其 `instrument(tracer_provider=...)`。不等于对所有函数插桩。 |
| 手工装饰器接口 | [README.md:159–174](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/packages/phoenix-otel/README.md#L159-L174) | 展示 `tracer_provider.get_tracer(...)` 后使用 `@tracer.chain`、`@tracer.tool`。实现来自继承的 OpenInference 层；本仓库不能单独证明装饰器内部的全部边界行为。 |
| OTel 传输原语 | [otel.py:13–23](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/packages/phoenix-otel/src/phoenix/otel/otel.py#L13-L23) | HTTP/gRPC OTLP exporter、simple/batch processor 基于 OpenTelemetry 依赖，Phoenix 提供默认配置包装。 |

**Unknown**：外部 OpenInference 具体版本的 async generator、stream、异常、脱敏和 context propagation 实现，本次未追到它们的独立仓库，不将 README 例子当作已验证的实现结论。

## 2. OTLP receiver → 后台任务 → 内存队列 → 事务

```text
应用的手工装饰器 / 已安装的 OpenInference instrumentor
  → TracerProvider → SpanProcessor → OTLP exporter
  → Phoenix HTTP /v1/traces 或 gRPC Export
  → decode_otlp_span → 内存 deque
  → BulkInserter → insert_span → traces / spans
                            ↘ SpanCostCalculator → span_costs / span_cost_details
```

**Observed**：HTTP receiver 在 [traces.py:431–500](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/server/api/routers/v1/traces.py#L431-L500) 接受 protobuf，支持 gzip/deflate，校验失败返回错误。关键点是第 491 行把 `_add_spans` 放入 `background_tasks`，然后返回 HTTP 200。后台在 [traces.py:697–719](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/server/api/routers/v1/traces.py#L697-L719) 逐个解码入队。project 优先级为 HTTP header、OTLP resource attribute、默认值。

**Observed**：gRPC receiver 在 [grpc_server.py:33–52](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/server/grpc_server.py#L33-L52) 等待解码、入队，再返回响应；同样不等待 DB 提交。

**Observed**：`decode_otlp_span` 在 [trace/otel.py:97–134](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/trace/otel.py#L97-L134) 解出 trace/span/parent ID、起止时间、attributes、events、status，把扁平属性转换为内部嵌套结构；exception event 在第 145–155 行解码。

**Observed**：`BulkInserter` 在 [bulk_inserter.py:115–180](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/db/bulk_inserter.py#L115-L180) 维护 span `deque` 和活动批次，默认 `max_ops_per_transaction=100`。第 183–196 行创建后台 task，第 229–230 行 enqueue 只是 append。第 283–347 行按批处理，每个 span 有 savepoint，成本跟随成功插入的 span 一起提交。第 199–220 行 shutdown drain 有时间上限，未处理完会记录剩余数量。

**Observed**：HTTP 的容量检查在 [utils.py:39–47](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/server/api/routers/v1/utils.py#L39-L47) 满时返回 503；gRPC 在 [app.py:618–638](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/server/app.py#L618-L638) 返回 UNAVAILABLE。容量是配置的可选上限加请求入口检查，不应表述为天然持久化消息队列或严格逐 span 限流。

**Inferred**：HTTP 200 早于后台解码和入队，更早于数据库提交；gRPC 成功响应也只证明完成入队。进程在持久化前退出可能丢失记录。不能把 receiver 成功响应视为端到端审计落盘凭证。

## 3. 数据结构、Token 与成本

**Observed**：可运行的 SQLite DDL 不只是 PostgreSQL 示例，见 [sqlite_schema.sql:232–328](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/db/ddl/sqlite_schema.sql#L232-L328)。

| 表/对象 | 核心字段 | 源码 |
|---|---|---|
| Trace | project FK、唯一 trace_id、start_time、end_time、session FK；latency 从时间差计算 | [models.py:808–864](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/db/models.py#L808-L864) |
| Span | trace FK、唯一 span_id、parent_id、name、kind、start/end、attributes、events、status、自己的 prompt/completion token、子树累计 token/error | [models.py:867–900](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/db/models.py#L867-L900) |
| SpanCost | span/trace FK、model_id、prompt/completion/total 的 token 与成本，可为空 | [models.py:2853–2914](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/db/models.py#L2853-L2914) |
| SpanCostDetail | token_type、is_prompt、tokens、cost、cost_per_token | [models.py:2967–2987](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/db/models.py#L2967-L2987) |

**Observed**：prompt、工具入参/出参不必各有固定 SQL 列。通用值放 attributes；`input_value`/`output_value` 属性在 [models.py:902–943](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/db/models.py#L902-L943) 从 attributes 提取。实际能捕获多少取决于上游插桩，receiver 不会凭空补出缺失 prompt、工具参数或 usage。

**Observed**：`insert_span` 在 [insertion/span.py:224–281](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/db/insertion/span.py#L224-L281) 仅对 LLM kind 提取 prompt/completion token；缺失或异常转为 0。重复 span_id `DO_NOTHING`。第 289–321 行会向已到达的祖先传播累计值，处理 child 在 parent 后到达的情况；父后到时聚合已存在孩子。Trace 时间范围在第 159 行扩展。

**Inferred**：将所有 span 的 cumulative token 相加会重复计算父子节点；应聚合每个 LLM span 的 own usage，或者在一个明确的根节点上取 cumulative。Phoenix 的缺失 token 转 0 是事实，但 EvalForge 可保留 `usage_status=missing`，避免缺失记录看起来像免费调用。

**Observed**：成本不是直接读取服务商账单。计算资格见 [insertion/helpers.py:118–130](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/db/insertion/helpers.py#L118-L130)：要求 LLM kind 和非空 model_name。在 [span_cost_calculator.py:20–42](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/server/cost_tracking/span_cost_calculator.py#L20-L42) 根据 start_time 与属性查找模型，再计算明细。

**Observed**：模型匹配参考时间、model_name 正则与 provider，见 [cost_model_lookup.py:128–175](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/server/cost_tracking/cost_model_lookup.py#L128-L175)。明细优先，剩余总量回退见 [cost_details_calculator.py:119–191](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/server/cost_tracking/cost_details_calculator.py#L119-L191)。无价格 calculator 时 cost 保留 None。基础公式为 tokens × base_rate，见 [token_cost_calculator.py:14–22](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/server/cost_tracking/token_cost_calculator.py#L14-L22)。

**Proposed**：EvalForge 保存 provider usage 原值、估算标记、价格版本/生效时间与币种。被测 Agent 成本和裁判成本分开核算。未知价格显示“未知”，不能计入 $0 的平均值。

## 4. SQLite 可行性与边界

**Observed**：Phoenix 自身支持 SQLite + aiosqlite。连接 pragma 在 [engines.py:53–78](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/db/engines.py#L53-L78)：busy_timeout=10000、foreign_keys=ON、WAL；同时当前固定版本设 `synchronous=OFF`。

**Observed**：写 engine 在 [engines.py:297–332](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/db/engines.py#L297-L332) 用独占 checkout 的单连接 QueuePool，而非允许并发 session 共享连接的 StaticPool。只读 engine 在 [engines.py:224–262](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/src/phoenix/db/engines.py#L224-L262) 有独立只读连接池。

**Proposed**：个人本地评测项目使用 SQLite 合理：单 writer、批量事务、trace/span 索引、WAL。EvalForge 不必复刻完整 OTLP collector，第一版可由自己的装饰器写入统一 trace sink。需要解释持久化确认、flush、队列容量、异常退出时的策略；审计数据可优先 `synchronous=NORMAL/FULL`，这是设计取舍，不是 Phoenix 已采用的配置。

**Unknown**：本机器支持的安全吞吐上限、P95 延迟、最大并发数、进程 kill 或断电损失窗口均未测试。不得从 SQLite 支持事实推导“无限扩展”或具体性能数字。

## 5. 许可证证据

| 位置 | 直接观察 |
|---|---|
| [根 LICENSE](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/LICENSE#L1-L18) | ELv2，包括托管/管理服务相关限制。 |
| [phoenix-otel/LICENSE](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/packages/phoenix-otel/LICENSE#L1-L9) | Apache License 2.0。 |
| [phoenix-otel/pyproject.toml:6–7](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/packages/phoenix-otel/pyproject.toml#L6-L7) | license 元数据为 Apache-2.0，并打包 LICENSE、IP_NOTICE。 |
| [phoenix-otel/IP_NOTICE](https://github.com/Arize-ai/phoenix/blob/9793e30feae1949f7bf972613aaf4275dc0b1b0b/packages/phoenix-otel/IP_NOTICE#L1-L5) | 声明部分代码专利信息，并仍写 ELv2，与子包前述声明不一致。 |

**Unknown**：子包元数据冲突的最终适用解释，本次未向维护者确认。不能将整个仓库概括为 Apache，也不做无保留的子包许可结论。本项目研究通用 tracing、树结构、usage 和批量入库机制，独立编写应用代码，不移植 Phoenix 服务端源码。

## 6. EvalForge 应验收的行为（设计建议）

- 同步、异步和嵌套工具调用能保持正确 trace_id / parent_span_id；异常会写 ERROR 并继续抛出原异常。
- 对重复 span_id 重放幂等；parent/child 乱序到达不会重复 token；用 own usage 汇总计费。
- 缺失 usage、未知模型价格和真实 0 用不同状态表示。
- 评测运行结束后可等待 flush；报告明确数据是否已提交。队列满和 flush 失败能被调用方识别。
- 保存输入/输出时执行可配置脱敏、大小限制；原始 SOP、Prompt 与工具参数的保留策略可核查。
- 雷达图展示归一化后的分值，旁边保留延迟毫秒、美元成本与原始指标；性能数值来自同一 dataset、相同运行配置和样本量。
