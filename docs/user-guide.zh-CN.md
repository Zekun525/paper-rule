# 用户手册

1. 在仓库外初始化私有目录：`paperrule init --workspace <私有目录>`。
2. 建立论文档案：`paperrule paper add --id <代号> --path <论文目录>`。
3. 导入 TXT/Markdown 意见：`paperrule ingest <文件> --paper <代号> --reviewer <来源代号>`。
4. 创建候选规则并通过本地 API 自由讨论。检查提案全文和哈希后才批准。
5. 对论文安装 Codex Skill：`paperrule install-codex --paper <论文目录>`。

PDF 原生批注提取需要可选 PyMuPDF；无文字批注不会自动补写意图。当前同步和回归测试持久化功能尚未提供。
