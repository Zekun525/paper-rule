type Coverage = {
  rule_id: string; rule_version: number;
  status: 'checked' | 'not_reviewed' | 'unavailable';
  checked_line_count: number; reason: string;
};
export type ReviewEvidenceData = {
  memory_commit?: string | null; memory_rules_dirty?: boolean | null;
  rule_snapshot_sha256?: string | null;
  rule_snapshot?: { id: string; version: number; short_title: string; statement: string }[];
  coverage?: Coverage[];
  files?: { path: string; sha256: string; diff: string }[];
  diff_mode?: boolean; semantic_status?: string; latex_build_status?: string;
  fixed_items?: string[];
};

const statuses: Record<string, string> = {
  checked: '已执行检查', not_reviewed: '未审查', unavailable: '无法执行',
  not_run: '未运行', passed: '通过', failed: '失败', incomplete: '尚未完成',
};
const reasons: Record<string, string> = {
  deterministic_phrase_check: '执行了确定性短语检查',
  semantic_not_reviewed: '尚未执行语义审查',
  deterministic_check_not_supported: '当前检查器不支持这条规则',
  no_lines_in_selected_input: '所选输入中没有可检查的文本行',
};
const describe = (value?: string) => value ? statuses[value] ?? value : '报告未记录';

export function ReviewEvidence({ report }: { report: ReviewEvidenceData }) {
  const coverage = report.coverage ?? [];
  const snapshot = report.rule_snapshot ?? [];
  const files = report.files ?? [];
  return <section aria-label="审查范围与版本依据">
    <h4>审查范围与版本依据</h4>
    <p className="muted">以下信息来自这份报告。导入外部报告不会重新运行检查；“已执行检查”也不代表没有发现问题或已完成全文审查。</p>
    <p>规则库提交：{report.memory_commit || '报告未记录'}</p>
    <p>规则快照哈希：{report.rule_snapshot_sha256 || '报告未记录'}</p>
    {report.memory_rules_dirty === true && <p className="warning">报告记录：检查时存在未提交的规则，所列 Git 提交不能单独代表当时使用的全部规则内容。</p>}
    {report.memory_rules_dirty === false && <p>报告记录：检查时规则目录与所列 Git 提交一致。</p>}
    {report.memory_rules_dirty == null && <p>报告未记录规则目录是否存在未提交修改。</p>}
    <p>输入范围：{report.diff_mode === true ? '变更区域' : report.diff_mode === false ? '所提供的文本文件' : '报告未记录'}</p>
    <p>语义审查：{describe(report.semantic_status)}；LaTeX 构建：{describe(report.latex_build_status)}</p>
    <h5>逐条规则检查记录</h5>
    {coverage.length ? <>
      <p>报告列出 {coverage.length} 条规则：已执行 {coverage.filter(item => item.status === 'checked').length} 条，未审查 {coverage.filter(item => item.status === 'not_reviewed').length} 条，无法执行 {coverage.filter(item => item.status === 'unavailable').length} 条。</p>
      {coverage.map((item, index) => <article className="evidence" key={item.rule_id + ':' + index}>
        <p>{item.rule_id} · v{item.rule_version} · {describe(item.status)}</p>
        <p>已检查文本行数：{item.checked_line_count}；原因：{reasons[item.reason] ?? item.reason ?? '报告未记录'}</p>
      </article>)}
    </> : <p>这份报告没有逐条检查记录，无法据此确认哪些规则已经检查。</p>}
    <h5>使用的规则内容</h5>
    {snapshot.length ? <details>
      <summary>查看 {snapshot.length} 条历史规则快照</summary>
      {snapshot.map((rule, index) => <article className="evidence" key={rule.id + ':' + index}>
        <p>{rule.id} · v{rule.version} · {rule.short_title}</p>
        <p>{rule.statement}</p>
      </article>)}
    </details> : <p>报告未保存规则内容快照。</p>}
    <h5>输入文件与修改对比</h5>
    {files.length ? files.map((file, index) => <article className="evidence" key={file.path + ':' + index}>
      <p>文件：{file.path}</p>
      <p>SHA-256：{file.sha256}</p>
      {file.diff ? <details><summary>查看 {file.path} 的修改对比</summary>
        <pre className="diff">{file.diff}</pre>
      </details> : <p>该文件没有记录修改前后对比。</p>}
    </article>) : <p>报告未列出输入文件及其内容哈希。</p>}
    <h5>报告记录的已修复项</h5>
    {(report.fixed_items ?? []).length
      ? report.fixed_items!.map((item, index) => <p key={index}>{item}</p>)
      : <p>报告未记录已修复项。</p>}
  </section>;
}
