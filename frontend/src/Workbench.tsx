import { useEffect, useRef, useState } from 'react';
import { request } from './api';
import { Sources } from './Sources';
import { Approvals } from './Approvals';
import { RuleEditor } from './RuleEditor';
import { Rules } from './Rules';
import { Regression } from './Regression';
import { Papers } from './Papers';
import { Settings } from './Settings';
import type { Rule, Proposal, Source, Feedback, Paper } from './types';

export default function Workbench() {
  const [page, setPage] = useState('工作台');
  const [rules, setRules] = useState<Rule[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [feedback, setFeedback] = useState<Feedback[]>([]);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [selected, select] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState(false);
  const running = useRef(false);
  const reload = async () => {
    const [a,b,c,d,e] = await Promise.all([
      request<Rule[]>('/rules'), request<Proposal[]>('/proposals'),
      request<Source[]>('/sources'), request<Feedback[]>('/feedback'), request<Paper[]>('/papers'),
    ]);
    setRules(a); setProposals(b); setSources(c); setFeedback(d); setPapers(e);
  };
  useEffect(() => { void reload().catch(e => setError(e.message)); }, []);
  const run = (task: () => Promise<void>) => {
    if (running.current) return;
    running.current = true; setBusy(true); setError('');
    void task().catch(e => setError(e instanceof Error ? e.message : '操作失败，请重试。'))
      .finally(() => { running.current = false; setBusy(false); });
  };
  const create = async (rule: Rule) => {
    const proposal = await request<Proposal>('/proposals', { rule, feedback_ids: rule.source_feedback_ids ?? [] });
    await reload(); select(proposal.proposal_id); setDraft(false); setPage('审批中心');
  };
  return <div className="shell workbench">
    <aside><div className="brand"><b>PaperRule</b></div>
      <nav aria-label="主导航">{['工作台', '来源与意见', '审批中心', '规则知识库', '论文工作区', '回归测试', '设置与诊断'].map(title =>
        <button key={title} className={page === title ? 'active' : ''} onClick={() => setPage(title)}>{title}</button>
      )}</nav><small>本机私有记忆</small>
    </aside>
    <main aria-busy={busy}>
      <header><div><h1>{page}</h1><p>保留依据，讨论规则，由你决定何时生效。</p></div>
        <button disabled={busy} onClick={() => run(reload)}>刷新数据</button>
      </header>
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">正在处理，请稍候…</p>}
      {page === '工作台' && <section className="panel">
        <h2>你的规则记忆</h2>
        <p>{sources.length} 份来源 · {feedback.length} 条意见 · {rules.filter(r => r.status === 'active').length} 条生效规则</p>
        <button onClick={() => setPage('来源与意见')}>导入意见</button>
        <button onClick={() => setDraft(!draft)}>新建规则提案</button>
        {draft && <RuleEditor busy={busy} save={rule => run(() => create(rule))} />}
      </section>}
      {page === '来源与意见' && <Sources sources={sources} feedback={feedback} papers={papers} reload={reload} create={create} run={run} busy={busy} />}
      {page === '审批中心' && <Approvals proposals={proposals} feedback={feedback} selected={selected} select={select} reload={reload} run={run} busy={busy} />}
      {page === '规则知识库' && <Rules rules={rules} feedback={feedback} busy={busy} run={run} open={async proposal => {
        await reload(); select(proposal.proposal_id); setPage('审批中心');
      }} />}
      {page === '回归测试' && <Regression rules={rules} papers={papers} busy={busy} run={run} />}
      {page === '论文工作区' && <Papers papers={papers} busy={busy} reload={reload} run={run} />}
      {page === '设置与诊断' && <Settings busy={busy} run={run} open={async proposal => {
        await reload();
        select(proposal.proposal_id);
        setPage('审批中心');
      }} />}
    </main>
  </div>;
}
