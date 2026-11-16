# PaperRule

PaperRule 将经人工批准的学术写作规范与公开代码隔离保存，并把来源意见、适用范围、提案修订和审批事件串成可追溯记录。聊天记录不会自动修改生效规则。

## 快速开始

需要 Python 3.12+，在项目目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,ingest]"
paperrule doctor
paperrule init --workspace "$HOME\paperrule-memory"
paperrule app
```

API 文档位于 `http://127.0.0.1:8765/docs`。React/Vite 源码位于 `frontend/`，构建需要 Node/npm。

```powershell
paperrule paper add --id sample-paper --path . --research-type information-theory --venue TIT --article-type full
paperrule ingest .\examples\feedback.txt --paper sample-paper --reviewer advisor_01
paperrule rules search proof
paperrule install-codex --paper .
```

使用 `paperrule proposal draft G-001 "证明清晰度" "说明每一步推导依据"` 创建候选规则；在讨论并审阅完整版本后，再通过 `/api/proposals/{id}/approve` 或 CLI 显式审批。

## 隐私边界

记忆库使用本地用户选择的目录，默认位于用户数据目录。仓库示例均为合成内容。默认不连接 AI，也不上传私有资料。不要将论文、导师意见或真实规则库放进本仓库。

## 当前实现范围

当前版本提供 JSON 私有记忆、证据保留的文本/PDF/DOCX 导入、严格数据模型、审批门槛、内容哈希与基线检查、本地 Git 权威存储、作用域检索、localhost FastAPI、基础 CLI、React 审批界面、确定性回归案例和明确标记的离线 Provider。可选模型 Provider、SQLite/FTS 和浏览器 E2E 仍作为后续工作；系统不会把离线结果伪称语义审查。

## 开发测试

```powershell
python -m pip install -e ".[dev,ingest]"
pytest -q
python -m ruff check src tests
```
