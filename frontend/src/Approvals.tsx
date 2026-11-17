import { useEffect, useState } from 'react';
import { request } from './api';
import type { Feedback, Proposal } from './types';
import { closed, label } from './types';
import { RuleEditor } from './RuleEditor';
import { BatchRules } from './BatchRules';

export function Approvals({ proposals, feedback, selected, select, reload, run, busy }: { proposals: Proposal[]; feedback: Feedback[]; selected: string; select: (id: string) => void; reload: () => Promise<void>; run: (task: () => Promise<void>) => void; busy: boolean }) {
  const [message, setMessage] = useState(''), [reason, setReason] = useState(''), [edit, setEdit] = useState(false), [diff, setDiff] = useState('');
  const p = proposals.find(item => item.proposal_id === selected) ?? proposals[0];
  useEffect(() => { setEdit(false); setDiff(''); setMessage(''); setReason(''); }, [p?.proposal_id]);
  const decide = (action: string) => run(async () => { if (!p) return; await request('/proposals/' + p.proposal_id + '/' + action, action === 'approve' ? { proposal_hash: p.proposal_hash } : { reason }); await reload(); });
  return <div className="approval-grid"><section className="panel"><h2>提案档案（{proposals.length}）</h2>{proposals.map(item => <button className={'record ' + (item.proposal_id === p?.proposal_id ? 'chosen' : '')} key={item.proposal_id} onClick={() => select(item.proposal_id)}><b>{item.after.short_title}</b><small>{label(item.status)} · 第 {item.revision} 版</small></button>)}{!proposals.length && <p className="empty">从意见创建提案，或在工作台新建规则。</p>}</section>
    {p && <section className="panel"><h2>{p.after.short_title}</h2><p className="muted">{label(p.status)} · 第 {p.revision} 版 · {p.after.id}</p><p className="statement">{p.after.statement}</p><p>适用范围：{p.after.scope.levels.join(', ')} {(p.after.scope.paper_ids ?? []).join(', ')} {(p.after.scope.sections ?? []).join(', ')}</p><p>{p.recommendation}</p><details><summary>影响范围和依据</summary>{p.impact.map((s, i) => <p key={i}>{s}</p>)}{feedback.filter(f => p.feedback_ids.includes(f.id) || p.after.source_feedback_ids?.includes(f.id)).map(f => <blockquote key={f.id}>{f.quote}<small>{f.reviewer_id} · {f.id}</small></blockquote>)}<p>当前全局强制规则不会因为讨论而自动改写。</p></details>
    <BatchRules proposal={p} />
    <button disabled={busy} onClick={() => run(async () => { const result = await request<{ diff: string }>('/proposals/' + p.proposal_id + '/diff'); setDiff(result.diff); })}>查看修改对比</button>{diff && <pre className="diff">{diff}</pre>}
    {!closed.has(p.status) && <><button disabled={busy} onClick={() => setEdit(!edit)}>{edit ? '收起编辑' : '直接修改提案'}</button>{edit && <RuleEditor key={p.proposal_hash} initial={p.after} busy={busy} save={rule => run(async () => { await request('/proposals/' + p.proposal_id + '/chat', { message: '人工修订提案', revised: rule }); await reload(); setEdit(false); })} />}
    <label>拒绝或暂缓的原因<input value={reason} onChange={e => setReason(e.target.value)} /></label><div className="actions"><button disabled={busy} onClick={() => decide('defer')}>暂缓</button><button disabled={busy} onClick={() => decide('reject')}>拒绝</button><button disabled={busy} className="primary" onClick={() => decide('approve')}>批准当前第 {p.revision} 版</button></div><p className="muted">批准后才会生效。若已有其他规则更新，需重新核对提案。</p></>}
    <details><summary>提案版本记录</summary>{p.revisions.map(r => <article className="evidence" key={r.revision}><b>第 {r.revision} 版</b><p>{r.after.statement}</p><p>{r.after.scope.levels.join(', ')}</p></article>)}</details></section>}
    {p && <section className="panel"><h2>自由讨论</h2>{p.chat.map((turn, i) => <div className="turn" key={i}><b>你的意见</b><p>{turn.user_text}</p><b>{turn.provider === 'manual' ? '已保存人工修订' : 'AI 回复'}</b><p>{turn.assistant_text}</p>{turn.error && <p className="warning">本轮 AI 未完成有效分析，可重试或直接编辑。</p>}</div>)}{!p.chat.length && <p className="muted">可提出修改、追问和反对意见。聊天中的同意不会自动批准规则。</p>}
    <form onSubmit={e => { e.preventDefault(); run(async () => { await request('/proposals/' + p.proposal_id + '/chat', { message }); setMessage(''); await reload(); }); }}><label>讨论内容<textarea required rows={5} value={message} onChange={e => setMessage(e.target.value)} disabled={closed.has(p.status)} /></label><button disabled={busy || closed.has(p.status) || !message.trim()} className="primary">发送讨论</button></form></section>}
  </div>;
}
