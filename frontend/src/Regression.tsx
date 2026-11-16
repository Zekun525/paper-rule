import { useEffect, useState } from 'react';
import { request } from './api';
import type { Paper, Rule, Run } from './types';
import { label } from './types';

type Case = {
  id: string; rule_id: string; rule_version?: number; input_text: string; expected: string;
  check_method: 'deterministic' | 'semantic'; explanation: string; paper_id: string | null;
};
type Props = { rules: Rule[]; papers: Paper[]; busy: boolean; run: (task: () => Promise<void>) => void };
const reasons: Record<string, string> = {
  rule_not_found: '关联规则不存在', rule_not_active: '关联规则尚未生效',
  rule_version_mismatch: '规则版本已经变化，请复核案例', rule_outside_scope: '规则不适用于此论文或章节',
  semantic_provider_unavailable: '语义审查尚未执行', deterministic_check_not_supported: '此规则尚无可运行的固定词句检查',
  unknown_expected_behavior: '案例的预期结果无法识别',
};

export function Regression({ rules, papers, busy, run }: Props) {
  const [cases, setCases] = useState<Case[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState('');
  const [paper, setPaper] = useState('');
  const [ruleId, setRuleId] = useState('');
  const [text, setText] = useState('');
  const [expected, setExpected] = useState('violation');
  const [explanation, setExplanation] = useState('');
  const selectedRule = rules.find(rule => rule.id === ruleId);
  const load = async () => {
    const [a, b] = await Promise.all([request<Case[]>('/regression/cases'), request<Run[]>('/regression/runs')]);
    setCases(a); setRuns(b);
  };
  useEffect(() => { void load().catch(e => setError(e.message)); }, []);
  return <div className="page-grid">
    <section className="panel">
      <h2>历史案例集（{cases.length}）</h2>
      {error && <p role="alert">{error}</p>}
      <form onSubmit={e => { e.preventDefault(); run(async () => {
        await request('/regression/cases', {
          id: 'CASE-' + crypto.randomUUID(), rule_id: ruleId, rule_version: selectedRule?.version,
          input_text: text, expected, explanation, paper_id: paper || null,
          check_method: selectedRule?.check_method === 'deterministic' ? 'deterministic' : 'semantic',
        });
        await load(); setText(''); setExplanation('');
      }); }}>
        <label htmlFor="regression-rule">关联规则</label><select id="regression-rule" required value={ruleId} onChange={e => setRuleId(e.target.value)}>
          <option value="">请选择生效规则</option>
          {rules.filter(rule => rule.status === 'active').map(rule =>
            <option key={rule.id} value={rule.id}>{rule.short_title} · v{rule.version}</option>)}
        </select>
        <label>关联论文 / 运行范围<select value={paper} onChange={e => setPaper(e.target.value)}>
          <option value="">不指定论文</option>
          {papers.map(p => <option key={p.paper_id} value={p.paper_id}>{p.title || p.paper_id}</option>)}
        </select></label>
        <label>待检查的例句<textarea required rows={4} value={text} onChange={e => setText(e.target.value)} /></label>
        <label>正确的预期结果<select value={expected} onChange={e => setExpected(e.target.value)}>
          <option value="violation">应该发现问题</option><option value="clean">不应该误报</option>
        </select></label>
        <label>判定依据<textarea value={explanation} onChange={e => setExplanation(e.target.value)} /></label>
        <button className="primary" disabled={busy || !selectedRule}>保存回归案例</button>
      </form>
      <p className="muted">正面和问题案例分别保存。规则版本变化后，旧案例会提示复核，不会悄悄当作通过。</p>
      {cases.map(c => <article className="evidence" key={c.id}>
        <b>{c.rule_id} · v{c.rule_version ?? '未固定版本'}</b><p>{c.input_text}</p>
        <p>{c.expected === 'violation' ? '应该发现问题' : '不应该误报'}</p><small>{c.explanation}</small>
      </article>)}
    </section>
    <section className="panel">
      <h2>检查运行历史</h2>
      <p>语义审查尚未执行的案例会保留为未检查；空案例集也不代表检查通过。</p>
      <button disabled={busy} onClick={() => run(async () => {
        await request('/regression/runs', { paper_id: paper }); await load();
      })}>运行已保存案例</button>
      {runs.map(r => <article className="evidence" key={r.run_id}>
        <h3>{label(r.status)}</h3><p>{r.total} 个案例：{r.passed} 通过，{r.failed} 失败，{r.unavailable} 未检查</p>
        <small>{new Date(r.created_at).toLocaleString()}</small>
        <div className="actions">
          <a href={'/api/regression/runs/' + r.run_id + '/report?format=json'}>导出 JSON</a>
          <a href={'/api/regression/runs/' + r.run_id + '/report?format=markdown'}>导出 Markdown</a>
        </div>
        <details><summary>逐项结果</summary>{r.results.map(item =>
          <p key={item.id}>{item.id}：{label(item.status)} {item.reason ? reasons[item.reason] ?? '需要人工复核' : ''}</p>)}
        </details>
      </article>)}
      {!runs.length && <p className="empty">还没有运行记录。保存案例后即可开始检查。</p>}
    </section>
  </div>;
}
