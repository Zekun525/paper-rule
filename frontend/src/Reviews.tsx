import { useEffect, useState } from 'react';
import { request } from './api';

type Finding = {
  rule_id: string; rule_version: number; location: string; quote: string;
  description: string; evidence: string; recommendation: string; review_type: string;
  confirmed: boolean | null;
};
type Report = {
  review_id: string; paper_id: string | null; task_summary: string;
  paper_commit: string | null; section: string; task: string;
  provider: string; model: string; source: string; status: string;
  created_at: string; findings: Finding[]; unresolved: string[];
};
type Props = {
  paperId: string; busy: boolean; run: (task: () => Promise<void>) => void;
};

export function Reviews({ paperId, busy, run }: Props) {
  const [reports, setReports] = useState<Report[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [input, setInput] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    let active = true;
    setReports([]); setSelectedId(''); setInput(''); setError(''); setSaved(false);
    if (!paperId) { setLoading(false); return; }
    setLoading(true);
    void request<Report[]>('/reviews')
      .then(items => { if (active) setReports(items.filter(item => item.paper_id === paperId)); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : '读取审查记录失败。'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [paperId]);
  const selected = reports.find(item => item.review_id === selectedId) ?? reports[0];
  const reload = async () => {
    const items = await request<Report[]>('/reviews');
    setReports(items.filter(item => item.paper_id === paperId));
  };
  return <section className="panel">
    <h2>论文审查记录</h2>
    <p className="muted">使用上方“选择已保存论文”切换记录。导入的报告保留原始判断；保存报告不会批准规则，也不表示整篇论文已通过审查。</p>
    {error && <p role="alert">{error}</p>}
    {!paperId && <p className="empty">请先选择已保存的论文。</p>}
    {paperId && <>
      <button disabled={busy || loading} onClick={() => run(reload)}>刷新审查记录</button>
      {loading && <p role="status">正在读取审查记录…</p>}
      {reports.map(report => <button className="record" key={report.review_id}
        disabled={busy} onClick={() => setSelectedId(report.review_id)}>
        <b>{report.task_summary || report.review_id}</b>
        <small>{report.review_id} · {report.findings.length} 项发现 · {report.created_at}</small>
      </button>)}
      {!loading && !reports.length && <p className="empty">这篇论文尚无已保存的审查报告。</p>}
      {selected && <article className="evidence">
        <h3>{selected.task_summary || selected.review_id}</h3>
        <p>报告编号：{selected.review_id}</p>
        <p>来源记录：{selected.source} · {selected.provider} · {selected.model || '未记录模型'}</p>
        <p>报告原始状态：{selected.status}；此状态由报告提供方记录，尚不能代替完整验收。</p>
        <p>章节：{selected.section || '未指定'}；任务：{selected.task || '未指定'}</p>
        <p>论文提交：{selected.paper_commit || '报告未记录论文提交'}</p>
        <div className="actions">
          <a href={'/api/reviews/' + encodeURIComponent(selected.review_id) + '/report'}>导出审查 JSON</a>
          <a href={'/api/reviews/' + encodeURIComponent(selected.review_id) + '/report?format=markdown'}>导出审查 Markdown</a>
        </div>
        {selected.findings.map((finding, index) => <article className="evidence" key={index}>
          <h4>{finding.description}</h4>
          <p>规则：{finding.rule_id} · v{finding.rule_version}；位置：{finding.location || '报告未提供定位'}</p>
          <p>检查类型：{finding.review_type === 'semantic' ? '语义审查' : finding.review_type === 'deterministic' ? '确定性检查' : finding.review_type}</p>
          <p>人工确认：{finding.confirmed === true ? '已确认' : finding.confirmed === false ? '未认可此判断' : '尚未确认'}</p>
          <blockquote>{finding.quote || '报告未提供原文片段'}</blockquote>
          <p>依据：{finding.evidence || '报告未提供依据'}</p>
          <p>建议：{finding.recommendation || '报告未提供修改建议'}</p>
        </article>)}
        {!selected.findings.length && <p>本报告没有记录问题；这不表示全部适用规则均已检查。</p>}
        <h4>待人工确认的问题</h4>
        {selected.unresolved.map((item, index) => <p key={index}>{item}</p>)}
        {!selected.unresolved.length && <p>报告未列出待确认项。</p>}
      </article>}
      <form onSubmit={event => {
        event.preventDefault(); setSaved(false);
        run(async () => {
          if (new TextEncoder().encode(input).length > 1024 * 1024) {
            throw new Error('审查 JSON 超过 1 MiB，请拆分后导入。');
          }
          let value: unknown;
          try { value = JSON.parse(input); }
          catch { throw new Error('审查报告不是有效的 JSON，请检查格式。'); }
          if (typeof value !== 'object' || value === null || !('paper_id' in value)
              || value.paper_id !== paperId) {
            throw new Error('报告的 paper_id 必须与当前选择的论文编号一致。');
          }
          const report = await request<Report>('/reviews/import', value);
          await reload(); setSelectedId(report.review_id); setSaved(true);
        });
      }}>
        <label htmlFor="review-json">导入结构化审查 JSON</label>
        <textarea id="review-json" required rows={8} disabled={busy}
          value={input} onChange={event => { setInput(event.target.value); setSaved(false); }} />
        <p className="muted">可粘贴外部写作助手生成的报告。系统会检查论文、规则编号、版本和作用域；已有报告不能被不同内容覆盖。</p>
        <button disabled={busy || !input.trim()} className="primary">保存审查报告</button>
      </form>
      {saved && <p role="status">审查报告已保存，生效规则没有改变。</p>}
    </>}
  </section>;
}
