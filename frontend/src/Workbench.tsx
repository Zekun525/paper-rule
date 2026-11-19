import { useEffect, useRef, useState } from 'react';
import { request } from './api';
import { Sources } from './Sources';
import { Approvals } from './Approvals';
import { RuleEditor } from './RuleEditor';
import { Rules } from './Rules';
import { Regression } from './Regression';
import { Papers } from './Papers';
import { Settings } from './Settings';
import { Tasks } from './Tasks';
import type { Rule, Proposal, Source, Feedback, Paper } from './types';

const navigation = [
  { title: '开始', pages: ['工作台', '来源与意见', '审批中心'] },
  { title: '写作', pages: ['规则知识库', '论文工作区', '论文修改任务'] },
  { title: '管理', pages: ['回归测试', '设置与诊断'] },
];
const descriptions: Record<string, string> = {
  '工作台': '把论文修改意见变成下次写作也用得上的规则。',
  '来源与意见': '粘贴意见或导入文件，再挑出值得长期保留的建议。',
  '审批中心': '先讨论和修改提案，再决定哪些规则生效。',
  '规则知识库': '查看已批准的规则、适用范围和原始依据。',
  '论文工作区': '为当前论文筛选适用规则，检查文稿并查看修改建议。',
  '论文修改任务': '集中处理只适用于当前论文的一次性修改。',
  '回归测试': '用示例复查现有规则是否仍然得到预期结果。',
  '设置与诊断': '管理 AI 服务、私有同步和规则恢复。',
};
const statusFinal = new Set(['approved', 'applied', 'rejected', 'deferred', 'synced', 'sync_pending', 'sync_conflict']);

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
  const [loaded, setLoaded] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const focusedPage = useRef(page);
  const running = useRef(false);
  const reload = async () => {
    const [a,b,c,d,e] = await Promise.all([
      request<Rule[]>('/rules'), request<Proposal[]>('/proposals'),
      request<Source[]>('/sources'), request<Feedback[]>('/feedback'), request<Paper[]>('/papers'),
    ]);
    setRules(a); setProposals(b); setSources(c); setFeedback(d); setPapers(e); setLoaded(true);
  };
  useEffect(() => { void reload().catch(e => setError(e.message)); }, []);
  useEffect(() => {
    if (focusedPage.current === page) return;
    focusedPage.current = page;
    heading.current?.focus();
  }, [page]);
  const run = (task: () => Promise<void>) => {
    if (running.current) return;
    running.current = true; setBusy(true); setError('');
    void task().catch(e => setError(e instanceof Error ? e.message : '操作失败，请重试。'))
      .finally(() => { running.current = false; setBusy(false); });
  };
  const create = async (rule: Rule, operation = 'create') => {
    const proposal = await request<Proposal>('/proposals', { rule, operation, feedback_ids: rule.source_feedback_ids ?? [] });
    await reload(); select(proposal.proposal_id); setDraft(false); setPage('审批中心');
  };
  const pending = proposals.filter(item => !statusFinal.has(item.status));
  const activeRules = rules.filter(rule => rule.status === 'active');
  const next = pending.length ? {
    title: '继续审核提案', text: `有 ${pending.length} 份提案等待决定。可以先修改内容和适用范围。`,
    action: () => { select(pending[0].proposal_id); setPage('审批中心'); },
  } : activeRules.length ? {
    title: '打开论文工作区', text: '选择一篇论文，用已批准的规则检查文稿。',
    action: () => setPage('论文工作区'),
  } : {
    title: feedback.length ? '整理已有意见' : '导入第一条意见',
    text: feedback.length ? '打开已保存的意见，挑选一条值得复用的建议，整理成规则提案。' : '先粘贴一条修改意见，或导入一份带批注的文档。',
    action: () => setPage('来源与意见'),
  };
  return <div className="shell workbench">
    <aside><div className="brand"><b>PaperRule</b><span>论文规则工作台</span></div>
      <nav aria-label="主导航">{navigation.map(group => <div className="nav-group" key={group.title}>
        <span>{group.title}</span>{group.pages.map(title => <button key={title}
          aria-current={page === title ? 'page' : undefined} className={page === title ? 'active' : ''}
          disabled={busy} onClick={() => setPage(title)}>{title}</button>)}
      </div>)}</nav><small>本机私有记忆</small>
    </aside>
    <main aria-busy={busy}>
      <header><div><h1 ref={heading} tabIndex={-1}>{page}</h1><p>{descriptions[page]}</p></div>
        <button disabled={busy} onClick={() => run(reload)}>{error && !loaded ? '重新连接' : '刷新数据'}</button>
      </header>
      {error && <div className="notice failure" role="alert"><strong>这一步没有完成</strong><p>{error}</p></div>}
      {(busy || (!loaded && !error)) && <p className="notice" role="status">{loaded ? '正在处理，请稍候…' : '正在读取本机资料…'}</p>}
      {page === '工作台' && loaded && <>
        <section className="home-hero" aria-labelledby="next-step">
          <span className="eyebrow">下一步</span>
          <h2 id="next-step">{next.title}</h2><p>{next.text}</p>
          <div className="actions"><button className="primary" disabled={busy} onClick={next.action}>
            {next.title === '导入第一条意见' ? '导入意见' : next.title}
          </button><button disabled={busy} onClick={() => setDraft(!draft)} aria-expanded={draft}>
            {draft ? '收起新建提案' : '新建规则提案'}
          </button></div>
        </section>
        {draft && <section className="panel"><h2>新建规则提案</h2><RuleEditor busy={busy} save={rule => run(() => create(rule))} /></section>}
        <div className="home-stats" aria-label="资料概况">
          {[[sources.length, '份来源'], [feedback.length, '条意见'], [pending.length, '份待审提案'], [activeRules.length, '条生效规则']].map(([count, title]) =>
            <div key={title}><strong>{count}</strong><span>{title}</span></div>)}
        </div>
        <section className="home-guide" aria-label="工作流程">
          {[
            ['01', '收集意见', '保留原话和出处，归档 PDF、Word 或文字意见。', '来源与意见'],
            ['02', '讨论并批准', '调整措辞、范围和例外，由你决定哪一版生效。', '审批中心'],
            ['03', '用规则检查论文', '把适用的规则带到当前论文，查看发现和依据。', '论文工作区'],
          ].map(([number, title, text, target]) => <button key={number} disabled={busy} onClick={() => setPage(target)}>
            <span>{number}</span><strong>{title}</strong><small>{text}</small>
          </button>)}
        </section>
      </>}
      {page === '来源与意见' && <Sources sources={sources} feedback={feedback} papers={papers} reload={reload} create={create} run={run} busy={busy} />}
      {page === '审批中心' && <Approvals proposals={proposals} feedback={feedback} selected={selected} select={select} reload={reload} run={run} busy={busy} rules={rules} />}
      {page === '规则知识库' && <Rules rules={rules} feedback={feedback} busy={busy} run={run} open={async proposal => {
        await reload(); select(proposal.proposal_id); setPage('审批中心');
      }} />}
      {page === '回归测试' && <Regression rules={rules} papers={papers} busy={busy} run={run} />}
      {page === '论文工作区' && <Papers papers={papers} busy={busy} reload={reload} run={run} openApprovals={() => setPage('审批中心')} />}
      {page === '论文修改任务' && <Tasks papers={papers} feedback={feedback} busy={busy} run={run}
        openProposal={id => { select(id); setPage('审批中心'); }} />}
      {page === '设置与诊断' && <Settings busy={busy} run={run} open={async proposal => {
        await reload();
        select(proposal.proposal_id);
        setPage('审批中心');
      }} />}
    </main>
  </div>;
}
