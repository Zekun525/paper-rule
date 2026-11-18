export type Scope = { levels: string[]; paper_ids?: string[]; sections?: string[]; venues?: string[]; article_types?: string[]; exceptions?: string[] };
export type RuleRelation = { type: string; target_id: string; status?: string };
export type Rule = { id: string; version: number; status: string; short_title: string; statement: string; scope: Scope; check_method?: string; source_feedback_ids?: string[]; rationale?: string; positive_example?: string; negative_example?: string; relations?: RuleRelation[] };
export type Proposal = { proposal_id: string; operation: string; after: Rule; before: Rule | null; revision: number; proposal_hash: string; status: string; feedback_ids: string[]; recommendation: string; impact: string[]; revisions: { revision: number; hash: string; after: Rule }[]; chat: { user_text: string; assistant_text: string; provider: string; error?: string }[] };
export type Source = { id: string; filename: string; extraction_status: string; warnings: string[]; kind: string; reviewer_id: string; paper_id?: string; created_at: string };
export type Feedback = { id: string; source_id: string; quote: string; reviewer_id: string; reviewer_role: string; paper_id: string | null; classification: string; corrections: { text: string; reason: string }[]; location: { page_index?: number; page?: number; section?: string } };
export type Paper = { paper_id: string; title: string; venue: string; research_type: string; article_type: string };
export type RegressionResult = {
  id: string; status: string; reason?: string; provider?: string; model?: string;
  prompt_version?: string; human_review?: string;
  judgment?: { verdict: string; explanation: string; quote: string };
  input_sha256?: string; rule_sha256?: string; case_sha256?: string;
  case_snapshot?: unknown; rule_snapshot?: unknown;
};
export type Run = { run_id: string; status: string; total: number; passed: number; failed: number; unavailable: number; created_at: string; results: RegressionResult[] };
export const closed = new Set(['applied', 'rejected', 'approved', 'synced', 'sync_pending', 'sync_conflict']);
export const labels: Record<string, string> = { discussing: '讨论中', deferred: '已暂缓', applied: '已生效', rejected: '已拒绝', active: '生效中', proposed: '待审批', deprecated: '已停用', ready: '已就绪', draft: '草稿', passed: '通过', failed: '失败', incomplete: '尚未完成全部检查', unavailable: '未检查', empty: '暂无案例', ready_for_review: '待人工核对', partial: '部分提取', pending_transcription: '待补录', local: '仅保存在本机', configured: '已配置远端', synced: '已同步', pending: '待同步', conflict: '需要处理冲突' };
export const label = (value: string) => labels[value] ?? value;
