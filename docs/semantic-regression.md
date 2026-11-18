# Semantic regression

Semantic regression uses the same server-side PAPERRULE_PROVIDER setting as proposal discussion: openai/openai_api or codex/codex_cli. Manual mode makes no model calls and semantic cases remain unavailable. FakeProvider never establishes semantic acceptance.

The existing regression run API and CLI call the configured adapter for semantic cases. These calls send the selected rule and case excerpt to the configured provider. Expected labels and case explanations are withheld from the judging prompt. Use synthetic cases for development and provider evaluation.

Each response must match a strict schema and the exact rule ID/version. A violation needs a nonempty, exact quote from the excerpt. Invalid responses, unavailable services and uncertain judgments do not count as passes. A model judgment remains pending human review; it is not a mathematical proof or an approval of any rule.

Reports retain case/rule snapshots, their canonical JSON hashes, provider/model and prompt version for successful or uncertain judgments. The input_sha256 field hashes the canonical JSON string representation of the excerpt. A reported pass means the model judgment matched the stored expected label. It does not establish that the label or model judgment is correct.

Memory snapshots are captured under the memory lock; model calls happen after releasing it, so waiting for a model does not prevent approvals. The captured rules and memory commit describe the run inputs even if another approval occurs meanwhile.

Current limitations: no automatic retries, cancellation, baseline comparison, human adjudication editor or automatic postapproval evaluation. Scripted-provider tests validate protocol behavior only. A separately executed real-provider evaluation is still required before product acceptance.
