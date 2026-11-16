import { useState } from 'react';
import { request } from './api';
import { RuleEditor } from './RuleEditor';
import type { Feedback, Proposal, Rule } from './types';
import { label } from './types';

type Props = {
  rules: Rule[]; feedback: Feedback[]; busy: boolean;
  run: (task: () => Promise<void>) => void;
  open: (proposal: Proposal) => Promise<void>;
};

export function Rules({ rules, feedback, busy, run, open }: Props) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('active');
  const [selected, setSelected] = useState<Rule>();
  const [history, setHistory] = useState<Rule[]>([]);
  const [editing, setEditing] = useState(false);
  const visible = rules.filter(r => (status === 'all' || r.status === status)
    && (r.id + ' ' + r.short_title + ' ' + r.statement).toLowerCase().includes(query.toLowerCase()));
  const choose = (rule: Rule) => run(async () => {
    const versions = await request<Rule[]>('/rules/' + encodeURIComponent(rule.id) + '/history');
    setSelected(rule); setHistory(versions); setEditing(false);
  });
  return <div className="page-grid">
    <section className="panel">
      <h2>规则知识库</h2>
      <label>搜索编号、标题或内容<input value={query} onChange={e => setQuery(e.target.value)} /></label>
      <label>规则状态<select value={status} onChange={e => setStatus(e.target.value)}>
        <option value="active">生效中</option><option value="all">全部状态</option><option value="deprecated">已停用</option>
      </select></label>
      {visible.map(rule => <button key={rule.id} className={'record ' + (selected?.id === rule.id ? 'chosen' : '')}
        disabled={busy} onClick={() => choose(rule)}>
        <b>{rule.short_title}</b><small>{rule.id} · v{rule.version} · {label(rule.status)}</small>
        <p>{rule.statement}</p>
      </button>)}
      {!visible.length && <p className="empty">没有符合条件的规则。批准提案后，生效规则会出现在这里。</p>}
    </section>
    <section className="panel">
      <h2>{selected?.short_title ?? '规则详情与历史'}</h2>
      {!selected && <p className="muted">选择规则，查看来源、适用范围和历次版本。修改、停用和回退都会创建新提案，需要另外批准。</p>}
      {selected && <>
        <p>{selected.statement}</p>
        <p>适用层级：{selected.scope.levels.join(', ')}</p>
        <p>论文：{selected.scope.paper_ids?.join(', ') || '不限制'}；章节：{selected.scope.sections?.join(', ') || '不限制'}</p>
        <p>期刊：{selected.scope.venues?.join(', ') || '不限制'}；文章类型：{selected.scope.article_types?.join(', ') || '不限制'}</p>
        <p>例外：{selected.scope.exceptions?.join('；') || '未设置'}</p>
        <details><summary>来源依据与正反例</summary>
          {feedback.filter(f => selected.source_feedback_ids?.includes(f.id)).map(f =>
            <blockquote key={f.id}>{f.quote}<small>{f.reviewer_id} · {f.id}</small></blockquote>)}
          <p>正面案例：{selected.positive_example || '尚未补充'}</p>
          <p>问题案例：{selected.negative_example || '尚未补充'}</p>
        </details>
        <div className="actions">
          <button disabled={busy} onClick={() => setEditing(!editing)}>修改规则提案</button>
          {selected.status === 'active' && <button disabled={busy} onClick={() => run(async () => {
            await open(await request<Proposal>('/proposals', {
              rule: selected, operation: 'deactivate', feedback_ids: selected.source_feedback_ids ?? [],
            }));
          })}>创建停用提案</button>}
        </div>
        {editing && <RuleEditor key={selected.id + selected.version} initial={selected} busy={busy} save={rule => run(async () => {
          await open(await request<Proposal>('/proposals', { rule, operation: 'amend', feedback_ids: rule.source_feedback_ids ?? [] }));
        })} />}
        <h3>版本记录</h3>
        {history.map((version, index) => <article className="evidence" key={version.version}>
          <b>版本 {version.version} · {label(version.status)}</b><p>{version.statement}</p>
          {index > 0 && <details><summary>与上一版本比较</summary>
            <p>此前：{history[index - 1].statement}</p><p>此版：{version.statement}</p>
            <p>此前范围：{history[index - 1].scope.levels.join(', ')} {history[index - 1].scope.paper_ids?.join(', ')}</p>
            <p>此版范围：{version.scope.levels.join(', ')} {version.scope.paper_ids?.join(', ')}</p>
          </details>}
          <button disabled={busy || version.version === selected.version} onClick={() => run(async () => {
            await open(await request<Proposal>('/rules/' + encodeURIComponent(version.id) + '/revert', { version: version.version }));
          })}>以此版本创建回退提案</button>
        </article>)}
      </>}
    </section>
  </div>;
}
