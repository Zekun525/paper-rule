# Codex integration

Run `paperrule install-codex --paper <latex-project> --scope repo` to add a managed PaperRule skill inside the paper project and a marked instruction block to its `AGENTS.md`. Existing instructions are preserved. The integration asks Codex to load approved context and report deterministic findings. It never approves proposals.

`--scope user` installs the skill in the selected user's `.agents/skills/paperrule` directory while adding the instruction block to the specified paper project. This writes outside the paper project; use it only when that location is authorized. For a workflow restricted to one workspace, use `--scope repo`. User-scope installation tests use a synthetic home directory. No installation into the real user home was performed for this project.

Remove the matching installation with `paperrule uninstall-codex --paper <latex-project> --scope repo` (or `--scope user` for a user installation). The installer preserves custom skills and refuses to remove edited instruction blocks without manual review. Installation does not create a paper profile automatically; create a profile separately before requesting context by paper ID.

Configuration detection in `paperrule doctor` and the web diagnostics does not establish an AI connection. A usable service must also pass a real request and response validation. API-compatible services use `OPENAI_BASE_URL`, `PAPERRULE_OPENAI_MODEL`, and `OPENAI_API_KEY`; these process environment settings do not require changing global Codex configuration. Keep keys out of chat, public source, and test evidence.

Select `PAPERRULE_PROVIDER=openai_api` for a Chat Completions-compatible service. The adapter name does not restrict the model vendor: set the exact model identifier offered by the configured service, including a DeepSeek model when that service grants access to it. Model availability and real response quality require separate verification. This adapter currently uses `/chat/completions`; a service exposing only `/responses` needs a separate protocol implementation.

Requests omit fixed sampling parameters to accommodate models with different parameter support. The adapter refuses redirects, bounds response reads, and rejects empty, truncated, tool-only or refused replies. A browser-style User-Agent accommodates gateways that reject urllib's default agent. Synthetic transport tests do not establish that every gateway or model works.
