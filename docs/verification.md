# 验证记录

日期：2026-10-14，Asia/Shanghai。Windows，PowerShell 7.6.5，Python 3.13.9。

## 自动化验证

- 独立 venv 中通过 start.ps1 -SetupOnly 实际安装 requirements.txt；依赖导入检查成功。
- start.ps1 -SkipInstall 在独立 venv 中实际启动 Uvicorn，使用全新 SQLite，自动生成 50 题与 100 次调用演示。
- `python -m pytest -q`：**25 passed，1 warning**。
- `python -m compileall -q evalforge examples`：通过。
- `node --check evalforge/static/app.js`：通过。
- `pip check`：No broken requirements found。
- 可启动示例 Agent 的 `/answer` 接口通过 TestClient smoke 检查。

测试覆盖严格 supported 分子、空声明、错 ID、伪造引用、错误 claims 类型、坏模型响应、坏 usage、坏候选数据、未知成本、Recall/P95、异常重抛、同步嵌套链路、异步并发隔离、50 题唯一性、DOCX 原文与字符位置、无文本 PDF 拒绝、导入→生成→审阅→回归→导出全流程。

真实协议分支用 HTTPX MockTransport 覆盖两个 HTTP Agent 与模型裁判，验证 10 次待测调用不接收 golden answer，裁判计费与 Agent 计费分开，运行快照包含模型/单价。MockTransport 是本地协议 fixture，不是线上模型评测证据。

上游警告：当前 Starlette TestClient 使用 httpx 时产生 StarletteDeprecationWarning，建议上游迁移到 httpx2。它不影响这次 25 项测试通过，也不代表生产请求失败。本项目未为隐藏警告修改全局过滤器。完整验证环境版本见 requirements-lock.txt。

## 浏览器验证

使用安装在本机的 Playwright Core 与 Chrome headless，连接上述独立 venv 启动的服务。桌面 1440×1100，窄屏 390×844。无 JavaScript pageerror，无 document 横向溢出（表格本身允许横向滚动）。已查看实际截图并检查布局。

通过 12 类流程：

1. 四个页面导航。
2. 测试题标准答案与来源证据弹窗。
3. 实际文件上传。
4. 候选集生成。
5. 人工确认操作。
6. 后台双版本回归及完成更新。
7. 无据声明筛选。
8. 逐声明证据展开。
9. 从回答进入 Trace，打开 Span 输入输出。
10. 错误 Trace ID 的受控提示。
11. 模型与 Agent 配置弹窗。
12. 手机宽度导航、指标与图表排版。

截图：screenshots/overview.png、screenshots/evidence.png。截图里的数值来自本地演示运行，仅供界面和流程验证，不能用于宣称真实 LogiGraph 的质量或速度。

## 未验证的边界

没有用户模型密钥与实际 LogiGraph 服务，未做真实在线语义裁判准确率、GraphRAG 对比、美元账单对账、大规模压测、跨进程追踪或崩溃后续跑测试。当前设计为单用户、单 Uvicorn worker 的本地项目；后续接入自己的 Agent 与经人工确认的业务测试集后，才能形成真实项目指标。
