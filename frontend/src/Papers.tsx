import { useState } from 'react';
import { request } from './api';
import { Reviews } from './Reviews';
import type { Paper, Rule } from './types';

type Profile = Paper & { project_path?: string | null };
type Bundle = {
  paper_id: string; section: string; task: string; memory_commit: string | null;
  rules: { rule: Rule; why_loaded: string }[];
  complete: boolean;
  mandatory_omitted: string[];
  excluded_rules: {
    rule_id: string; reason: string; by_rule_id?: string;
    by_rule_version?: number; rule_version?: number;
  }[];
  approved_relations?: {
    rule_id: string; rule_version: number; target_id: string; target_version: number;
    type: string; reason: string;
  }[];
  unresolved_conflicts?: { rule_ids: string[]; rule_versions: Record<string, number> }[];
  relation_issues?: { rule_id: string; target_id: string; reason: string }[];
  scope_issues?: { rule_id: string; reason: string }[];
};
type Props = {
  papers: Paper[]; busy: boolean;
  reload: () => Promise<void>;
  run: (task: () => Promise<void>) => void;
  openApprovals: () => void;
};
const emptyProfile = (): Profile => ({
  paper_id: '', title: '', research_type: '', venue: '', article_type: '', project_path: '',
});
const exclusionReasons: Record<string, string> = {
  'different paper': '适用于其他论文',
  'research type mismatch': '研究类型不匹配',
  'publication mismatch': '投稿期刊不匹配',
  'article type mismatch': '文章类型不匹配',
  'section not included': '不适用于当前章节',
  'task not included': '不适用于当前任务',
  'explicitly excluded': '命中了已批准的排除条件',
  'explicit include filter does not match': '额外适用条件不匹配',
  'scope filters require clarification': '额外适用或排除条件需要澄清',
  'rule is not active': '规则尚未生效或已停用',
  'rule is not effective yet': '尚未到规则的生效时间',
  'duplicate identifier': '同一规则已加载',
  'context budget exceeded': '超出本次规则包的条数或长度上限',
  approved_narrows: '本次采用了明确批准的限定规则',
  approved_exception_to: '本次采用了明确批准的例外规则',
  approved_supersedes: '本次采用了明确批准的替代规则',
};
const relationIssueReasons: Record<string, string> = {
  self_conflict: '规则不能与自身构成冲突，请检查关系。',
  missing_conflict_target: '关联的冲突规则不存在，请检查关系。',
  missing_override_target: '关系目标不存在，请核对目标规则。',
  self_override: '规则不能替代自身，请核对关系。',
  inactive_override_rule: '关系涉及尚未生效或已停用的规则，需要重新核对。',
  override_target_binding_missing: '这条历史关系缺少目标版本绑定，需要重新建立并审批。',
  override_target_binding_stale: '目标规则已更新，原关系需要重新核对和审批。',
  override_target_outside_context: '本次上下文没有包含关系目标，需要核对适用范围。',
  approved_override_cycle: '关系形成循环，需要讨论并审批解决方案。',
  ambiguous_rule_identifiers: '规则编号不唯一，当前无法可靠选择规则。',
  override_scope_equal: '限定或例外关系没有更窄的适用范围，需要重新核对。',
};

export function Papers({ papers, busy, reload, run, openApprovals }: Props) {
  const [draft, setDraft] = useState<Profile>(emptyProfile);
  const [editing, setEditing] = useState(false);
  const [paperId, setPaperId] = useState('');
  const [section, setSection] = useState('');
  const [task, setTask] = useState('revise');
  const [bundle, setBundle] = useState<Bundle>();
  const [saved, setSaved] = useState(false);
  return <div className="page-grid paper-workspace">
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
        {bundle.complete === false && <div role="alert" className="evidence">
          <h3>规则上下文不完整</h3>
          {!!bundle.mandatory_omitted.length && <>
            <p>以下必需规则尚未加载：{bundle.mandatory_omitted.join('、')}。</p>
            <p>请按章节和具体任务缩小范围后重新加载。在补齐这些规则之前，不能据此认定已经遵循全部适用要求。</p>
          </>}
          {!!bundle.unresolved_conflicts?.length && <>
            <h4>存在尚未解决的规则冲突</h4>
            <p>以下已生效规则同时适用，但记录了冲突关系。请讨论并明确批准解决方案；系统不会自动决定采用哪一条。</p>
            {bundle.unresolved_conflicts.map(conflict => <p key={conflict.rule_ids.join(':')}>
              {conflict.rule_ids.map(id => id + ' · v' + conflict.rule_versions[id]).join(' ↔ ')}
            </p>)}
          </>}
          {!!bundle.relation_issues?.length && <>
            <h4>需要核对规则关系</h4>
            {bundle.relation_issues.map((issue, index) => <p key={issue.rule_id + ':' + index}>
              {issue.rule_id} → {issue.target_id || '未指定规则'}：
              {relationIssueReasons[issue.reason] ??
                '这条规则关系需要重新核对，当前未据此排除规则。'}
            </p>)}
          </>}
          {!!bundle.scope_issues?.length && <>
            <h4>适用条件需要澄清</h4>
            <p>以下规则包含无法识别或未填完整的额外条件。请在规则知识库中创建修改提案，核对条件并明确批准后重新加载。</p>
            {bundle.scope_issues.map(issue => <p key={issue.rule_id}>
              <b>{issue.rule_id}</b>：{exclusionReasons[issue.reason] ?? '适用条件需要澄清'}
            </p>)}
          </>}
          {(!!bundle.unresolved_conflicts?.length || !!bundle.relation_issues?.length) && <button
            disabled={busy} onClick={openApprovals}>前往审批中心处理规则关系</button>}
        </div>}
        <p className="muted">规则快照：{bundle.memory_commit || '尚无规则提交'}</p>
        {!!bundle.approved_relations?.length && <section aria-label="本次适用的已批准关系">
          <h3>本次适用的已批准关系</h3>
          <p>以下关系解释本次规则选择；若上下文不完整，请先处理上方提示。</p>
          {bundle.approved_relations.map((relation, index) => <p
            key={relation.rule_id + ':' + relation.target_id + ':' + index}>
            {relation.rule_id} · v{relation.rule_version} → {relation.target_id} ·
            v{relation.target_version}：{exclusionReasons[relation.reason] ?? '已批准的规则关系'}
          </p>)}
        </section>}
        {bundle.rules.map(({ rule, why_loaded }) => <article className="evidence" key={rule.id}>
          <small>{rule.id} · v{rule.version}</small><h3>{rule.short_title}</h3><p>{rule.statement}</p>
          <p className="muted">{why_loaded === 'scope matches paper, section, and task'
            ? '适用条件匹配当前论文、章节和任务。' : why_loaded}</p>
        </article>)}
        {!bundle.rules.length && bundle.complete !== false && <p className="empty">当前没有适用的已批准规则；这不表示稿件已通过审查。</p>}
        {!!bundle.excluded_rules?.length && <details>
          <summary>查看未加载的规则及原因（{bundle.excluded_rules.length} 条）</summary>
          {bundle.excluded_rules.map((item, index) => <p key={item.rule_id + '-' + index}>
            <b>{item.rule_id}</b>：{exclusionReasons[item.reason] ?? item.reason}
            {item.by_rule_id && <span>
              {'；对应的局部规则：' + item.by_rule_id + ' · v' + item.by_rule_version}
            </span>}
          </p>)}
        </details>}
      </>}
    </section>
    <Reviews paperId={paperId} busy={busy} run={run} />
  </div>;
}
