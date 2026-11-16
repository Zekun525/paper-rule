import { useState } from 'react';
import { request } from './api';
import type { Paper, Rule } from './types';

type Profile = Paper & { project_path?: string | null };
type Bundle = {
  paper_id: string; section: string; task: string; memory_commit: string | null;
  rules: { rule: Rule; why_loaded: string }[];
};
type Props = {
  papers: Paper[]; busy: boolean;
  reload: () => Promise<void>;
  run: (task: () => Promise<void>) => void;
};
const emptyProfile = (): Profile => ({
  paper_id: '', title: '', research_type: '', venue: '', article_type: '', project_path: '',
});

export function Papers({ papers, busy, reload, run }: Props) {
  const [draft, setDraft] = useState<Profile>(emptyProfile);
  const [editing, setEditing] = useState(false);
  const [paperId, setPaperId] = useState('');
  const [section, setSection] = useState('');
  const [task, setTask] = useState('revise');
  const [bundle, setBundle] = useState<Bundle>();
  const [saved, setSaved] = useState(false);
  return <div className="page-grid">
    <section className="panel">
      <h2>论文档案</h2>
      <p className="muted">登记论文类型与投稿目标，用来筛选适用规则。填写项目路径只保存位置，不会读取或修改论文文件。</p>
      <button disabled={busy} onClick={() => {
        setDraft(emptyProfile()); setEditing(false); setSaved(false);
      }}>新建论文档案</button>
      {papers.map(paper => <button disabled={busy} className="record" key={paper.paper_id}
        onClick={() => {
          setDraft({ ...paper }); setEditing(true); setSaved(false);
          setPaperId(paper.paper_id); setBundle(undefined);
        }}>
        <b>{paper.title || paper.paper_id}</b>
        <small>{paper.paper_id} · {paper.venue || '尚未设置期刊'} · {paper.article_type || '尚未设置文章类型'}</small>
      </button>)}
      <form onSubmit={event => { event.preventDefault(); run(async () => {
        await request('/papers', draft); await reload();
        setEditing(true); setPaperId(draft.paper_id); setBundle(undefined); setSaved(true);
      }); }}>
        <label htmlFor="paper-id">论文编号</label>
        <input id="paper-id" required disabled={editing || busy}
          pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,100}" value={draft.paper_id}
          onChange={event => { setSaved(false); setDraft({ ...draft, paper_id: event.target.value }); }} />
        {([
          ['title', '论文标题'], ['research_type', '研究类型'],
          ['venue', '投稿期刊'], ['article_type', '文章类型'], ['project_path', '论文项目路径（可选）'],
        ] as const).map(([key, title]) => <div key={key}>
          <label htmlFor={'paper-' + key}>{title}</label>
          <input id={'paper-' + key} disabled={busy} value={draft[key] ?? ''}
            onChange={event => { setSaved(false); setDraft({ ...draft, [key]: event.target.value }); }} />
        </div>)}
        <button className="primary" disabled={busy}>保存论文档案</button>
      </form>
      {saved && <p role="status">论文档案已保存。预览将使用保存后的投稿目标和文章类型。</p>}
    </section>
    <section className="panel">
      <h2>预览适用规则</h2>
      <p className="muted">这里只显示已批准且匹配论文、章节与任务的规则。修改投稿目标后，请先保存档案再重新预览。</p>
      <form onSubmit={event => { event.preventDefault(); run(async () => {
        setBundle(undefined);
        setBundle(await request<Bundle>('/context', { paper_id: paperId, section, task }));
      }); }}>
        <label htmlFor="context-paper">选择已保存论文</label>
        <select id="context-paper" required value={paperId} disabled={busy}
          onChange={event => { setPaperId(event.target.value); setBundle(undefined); }}>
          <option value="">请选择论文</option>
          {papers.map(paper => <option key={paper.paper_id} value={paper.paper_id}>{paper.title || paper.paper_id}</option>)}
        </select>
        <label htmlFor="context-section">章节</label>
        <input id="context-section" disabled={busy} value={section}
          placeholder="例如 introduction 或 proof"
          onChange={event => { setSection(event.target.value); setBundle(undefined); }} />
        <label htmlFor="context-task">当前任务</label>
        <input id="context-task" disabled={busy} value={task}
          onChange={event => { setTask(event.target.value); setBundle(undefined); }} />
        <button disabled={busy || !paperId}>加载适用规则</button>
      </form>
      {bundle && <>
        <p>已加载 {bundle.rules.length} 条规则。</p>
        <p className="muted">规则快照：{bundle.memory_commit || '尚无规则提交'}</p>
        {bundle.rules.map(({ rule, why_loaded }) => <article className="evidence" key={rule.id}>
          <small>{rule.id} · v{rule.version}</small><h3>{rule.short_title}</h3><p>{rule.statement}</p>
          <p className="muted">{why_loaded === 'scope matches paper, section, and task'
            ? '适用条件匹配当前论文、章节和任务。' : why_loaded}</p>
        </article>)}
        {!bundle.rules.length && <p className="empty">当前没有适用的已批准规则；这不表示稿件已通过审查。</p>}
      </>}
    </section>
  </div>;
}
