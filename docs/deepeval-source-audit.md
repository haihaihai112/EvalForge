# DeepEval 声明评估与合成测试集源码审计

固定提交：`016946f6d770f8bc4e2f63f665140aea527d6641`，该提交 `pyproject.toml` 声明版本 4.2.8。以下是静态源码观察，未安装或执行 DeepEval。源码下载通过 git shallow sparse checkout 完成，未将第三方仓库打包进交付物。

REA 本地入口已验证为 `rea-agents` 6.4.0；其 `reverse-engineer-anything/SKILL.md` 明确要求完整源码仓库使用常规仓库分析工具。因此本次使用 Git、rg 和源文件逐行阅读，不将源码阅读包装成 REA 二进制反编译结果，也没有伪造 Evidence ID。

## 1. Faithfulness 不只是两次模型调用

入口 [faithfulness.py:113](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/metrics/faithfulness/faithfulness.py#L113)；常规同步路径在 141～147 行执行：

```text
retrieval_context → _generate_truths ──┐
actual_output    → _generate_claims ──┴→ _generate_verdicts
                                       → _calculate_score → _generate_reason
```

异步路径 [faithfulness.py:182](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/metrics/faithfulness/faithfulness.py#L182) 用 asyncio.gather 并行抽取 truths 与 claims，之后生成 verdict 和解释。默认还生成解释，因此常规路径可以包含四个模型生成阶段。实验性的 System One 分支在 135/176 行提前返回，不能把整个库一概描述成永远执行同一个两阶段算法。

声明提取模板 [generate_claims.txt](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/metrics/faithfulness/templates/generate_claims.txt) 要求按回答本身拆解，保留上下文，即使声明现实中错误也照实提取。它不负责替 Agent 修正事实。证据抽取在 [faithfulness.py:348](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/metrics/faithfulness/faithfulness.py#L348)，核验收到的是拼接后的 truths，而非直接传原始 context。

**EvalForge 取舍**：保留“拆声明→按证据核验”的分离，直接提供带 ID 的原文片段；不先压缩 truths，减少丢失限制条件和来源位置的风险。核验返回原文引用、片段 ID 和简短理由；本地验证引用确实存在。引用存在只是必要条件，语义蕴含仍依赖裁判与人工校准。

## 2. 默认计分与用户要求存在实质差异

| 观察 | 固定证据 | 含义 |
|---|---|---|
| penalize_ambiguous_claims 默认 False | [faithfulness.py:86](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/metrics/faithfulness/faithfulness.py#L86) | 未启用对模糊声明的处罚。 |
| borderline 包括上下文不足或未提到的声明 | [faithfulness_verdicts_guidelines_text_only.txt:5](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/templates/metrics/fragments/faithfulness_verdicts_guidelines_text_only.txt#L5) | 没有直接矛盾，不代表有据支持。 |
| 默认 passing = YES、BORDERLINE | [faithfulness.py:408](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/metrics/faithfulness/faithfulness.py#L408) | 默认分数不等同于严格 supported / all。 |
| 空 verdict 默认分数 1 | [qag.py:113](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/metrics/utils/qag.py#L113) | 空声明也可走到此默认值。 |
| 松 JSON 路径过滤不在词表中的 verdict | [qag.py:100](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/metrics/utils/qag.py#L100)、[qag.py:238](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/metrics/utils/qag.py#L238) | 该路径不能自动证明每个声明都拿到一个有效判定。 |

例如三条声明中一条有据、一条上下文不足、一条矛盾：按此提交默认 passing 定义，示意分数可为 2/3；EvalForge 的明确口径是 1/3。此例是计分规则推导，不是对真实模型运行结果的声称。

**EvalForge 实现**：仅 supported 计分；unsupported/contradicted 不计分；无声明返回 null 并交给拒答分类指标；重复/缺失声明 ID、错误 JSON 类型、伪造引用均为 evaluation_error，不删除坏判定后缩小分母。使用独立的 Pydantic schema，不调用 DeepEval 黑盒库。

## 3. Synthesizer 是一条质量加工流水线

| 阶段 | 关键源码 | 机制与边界 |
|---|---|---|
| 文档入口 | [synthesizer.py:423](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/synthesizer/synthesizer.py#L423) | generate_goldens_from_docs 配置 ContextGenerator 并委托 contexts 生成。 |
| 切块与 embedding | [doc_chunker.py:97](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/synthesizer/chunking/doc_chunker.py#L97) | 使用 loader、token splitter 和 Chroma；EvalForge 为轻量本地应用自行实现段落切块，未复制向量存储栈。 |
| 上下文扩展 | [context_generator.py:521](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/synthesizer/chunking/context_generator.py#L521) | 随机种子块加相似块，并保留来源信息；相似度并不证明逻辑上的多跳依赖。 |
| 初始问题 | [synthesizer.py:770](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/synthesizer/synthesizer.py#L770) | 从格式化上下文生成结构化 SyntheticData。 |
| 质量改写 | [synthesizer.py:1554](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/synthesizer/synthesizer.py#L1554) | critic 打分，不足则按反馈改写，最多固定次数；循环后仍 append，不能断言所有输出都达到质量阈值。 |
| 演化 | [synthesizer.py:1608](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/synthesizer/synthesizer.py#L1608) | 按配置权重 random.choices 选择演化模板，记录 evolution 类型。 |
| 多上下文与推理 | [template.py:723](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/synthesizer/templates/template.py#L723)、[template.py:771](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/synthesizer/templates/template.py#L771) | 指令要求使用所有上下文及多步逻辑；这是生成要求，不是经过形式验证的性质。 |
| 标准答案 | [synthesizer.py:868](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/synthesizer/synthesizer.py#L868) | 从 evolved input 与 context 再次生成 expected_output；机器生成标签仍需校验。 |

默认 [EvolutionConfig](https://github.com/confident-ai/deepeval/blob/016946f6d770f8bc4e2f63f665140aea527d6641/deepeval/synthesizer/config.py#L21) 包含 Reasoning、Multi-context、Concretizing、Constrained、Comparative、Hypothetical、In-Breadth 七类。不能只凭这些枚举声称默认一定生成“错误前提题/不可回答题”；EvalForge 为物流场景单独定义这些类别，并校验类别覆盖。

## 4. 落地映射

```text
文档与来源 → documents.py → datasets.py → candidate / 人工确认
                                   ↓ 数据集快照
Agent 适配器 → agents.py → service.py → evaluation.py → metrics.py
                              ↘ tracing.py → SQLite → 审计页面
```

当前交付保留来源、类型、标准答案、拒答预期、证据位置与版本指纹。真实模型每批生成候选题并做结构/原文校验；人工确认后用于回归。离线模板数据用于展示闭环，明确与真实合成数据及真实模型测量区分。

尚未验证：物流领域裁判与人工标签的一致率、跨模型稳定性、真实 LogiGraph 的准确性提升；需要用户的 Agent、模型配置和人工标注数据后才能得出这些结果。本次没有分析 Ragas，DeepEval 已覆盖用户给出的二选一核心参考。
