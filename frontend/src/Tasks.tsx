import { useEffect, useState } from 'react';
import { request } from './api';
import type { Feedback, Paper, PaperTask } from './types';

type Props = {
  papers: Paper[]; feedback: Feedback[]; busy: boolean;
  run: (task: () => Promise<void>) => void;
  openProposal: (id: string) => void;
};

export function Tasks({ papers, feedback, busy, run, openProposal }: Props) {
  const [tasks, setTasks] = useState<PaperTask[]>([]);
  const [paperId, setPaperId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    void request<PaperTask[]>('/tasks').then(records => {
      if (active) setTasks(records);
    }).catch(reason => {
      if (active) setError(reason instanceof Error ? reason.message : '任务加载失败，请重试。');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  const visible = tasks.filter(task => !paperId || task.paper_id === paperId);
  return <section className="panel">
    <h2>已审批的论文修改任务</h2>
    <p>这里保留仅针对一篇论文的修改要求。这些任务不会作为长期规则加载到其他论文。</p>
    <label htmlFor="task-paper-filter">按论文筛选任务</label>
    <select id="task-paper-filter" value={paperId}
      onChange={event => setPaperId(event.target.value)}>
      <option value="">全部论文</option>
      {papers.map(paper => <option key={paper.paper_id} value={paper.paper_id}>
        {paper.title || paper.paper_id}
      </option>)}
    </select>
    <button disabled={busy || loading} onClick={() => run(async () => {
      setLoading(true);
      try { setTasks(await request<PaperTask[]>('/tasks')); setError(''); }
      finally { setLoading(false); }
    })}>刷新任务</button>
    {loading && <p role="status">正在加载任务…</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && !tasks.length && <p className="empty">
      还没有已审批任务。确认一次性修改的内容和所属论文后，需要明确批准任务提案才会保存在这里。
    </p>}
    {!loading && tasks.length > 0 && !visible.length && <p>这篇论文暂无已审批任务。</p>}
    {visible.map(task => <article className="evidence" key={task.task_id}>
      <h3>{task.record.short_title}</h3>
      <p>适用论文：{papers.find(paper => paper.paper_id === task.paper_id)?.title || task.paper_id}</p>
      <p style={{ whiteSpace: 'pre-wrap' }}>{task.record.statement}</p>
      <button disabled={busy} onClick={() => openProposal(task.proposal_id)}>查看审批提案</button>
      <details>
        <summary>查看原始意见与审批依据</summary>
        <p>提案创建时间：{new Date(task.created_at).toLocaleString()}</p>
        <p>提案编号：{task.proposal_id}</p>
        <p>已审批版本指纹：<code>{task.proposal_hash}</code></p>
        {(task.record.source_feedback_ids ?? []).map(id => {
          const item = feedback.find(record => record.id === id);
          return item ? <div key={id}>
            <p>{item.reviewer_id} · {id}</p>
            <blockquote>{item.quote}</blockquote>
            {item.corrections.map((entry, index) => <p key={index}>
              后续补充：{entry.text}（{entry.reason}）
            </p>)}
          </div> : <p key={id}>原始意见当前不可用：{id}</p>;
        })}
      </details>
    </article>)}
  </section>;
}
