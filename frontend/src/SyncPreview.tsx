import { useEffect, useState } from 'react';
import { request } from './api';
import { label } from './types';
import type { Rule, Scope } from './types';

type Snapshot = {
  path: string; blob_sha: string; rule_sha256: string; rule: Rule;
};
type Preview = {
  status: string; local_commit: string; remote_commit: string; base_commit: string;
  upstream_ref: string; preview_sha256: string;
  working_tree_dirty: boolean; staged_changes: boolean;
  changes: {
    rule_id: string; kind: string;
    base: Snapshot | null; local: Snapshot | null; remote: Snapshot | null;
  }[];
};
type Props = {
  busy: boolean; remoteConfigured: boolean; resetToken: number;
  run: (task: () => Promise<void>) => void;
};
const states: Record<string, string> = {
  same: '两边的已提交版本相同',
  ahead: '本机有尚未同步的版本',
  behind: '远端有更新的版本',
  diverged: '两边都修改过，需要逐条核对',
};
const changes: Record<string, string> = {
  local_change: '仅本机记录改变', remote_change: '仅远端记录改变',
  both_changed: '两边的记录都改变',
};
const levels: Record<string, string> = {
  global: '通用', research_type: '研究类型', publication: '投稿目标',
  paper: '当前论文', section_task: '章节或任务',
};

function ScopeDetails({ scope }: { scope: Scope }) {
  const rows: [string, string[] | undefined][] = [
    ['层级', scope.levels.map(value => levels[value] ?? value)],
    ['论文', scope.paper_ids], ['研究类型', scope.research_types],
    ['投稿目标', scope.venues], ['文章类型', scope.article_types],
    ['章节', scope.sections], ['任务', scope.task_types],
    ['包含条件', scope.include], ['排除条件', scope.exclude],
    ['例外', scope.exceptions],
    ['生效时间', scope.effective_from ? [scope.effective_from] : undefined],
  ];
  return <dl className="sync-scope">
    {rows.filter(([, values]) => !!values?.length).map(([name, values]) =>
      <div key={name}><dt>{name}</dt><dd>{values!.join('；')}</dd></div>)}
  </dl>;
}

function Version({ title, snapshot }: { title: string; snapshot: Snapshot | null }) {
  return <section className="sync-version" aria-label={title}>
    <h4>{title}</h4>
    {snapshot ? <>
      <h5>{snapshot.rule.short_title}</h5>
      <p>{snapshot.rule.id} · v{snapshot.rule.version} · {label(snapshot.rule.status)}</p>
      <p>{snapshot.rule.statement}</p>
      <ScopeDetails scope={snapshot.rule.scope} />
      {snapshot.rule.rationale && <p>依据：{snapshot.rule.rationale}</p>}
      {!!snapshot.rule.source_feedback_ids?.length &&
        <p>来源意见编号：{snapshot.rule.source_feedback_ids.join('、')}</p>}
      <details><summary>查看这版规则的完整记录与校验值</summary>
        <p>记录位置：{snapshot.path}</p>
        <p>规则内容校验值：{snapshot.rule_sha256}</p>
        <p>原始记录校验值：{snapshot.blob_sha}</p>
        <pre>{JSON.stringify(snapshot.rule, null, 2)}</pre>
      </details>
    </> : <p>这个版本中没有此规则。</p>}
  </section>;
}

export function SyncPreview({ busy, remoteConfigured, resetToken, run }: Props) {
  const [preview, setPreview] = useState<Preview>();
  useEffect(() => { setPreview(undefined); }, [resetToken]);
  return <section aria-label="跨电脑规则差异预览">
    <h3>跨电脑规则差异预览</h3>
    <p>并排核对共同版本、本机版本和远端版本。读取预览不会替换已批准的规则。</p>
    <button disabled={busy || !remoteConfigured} onClick={() => run(async () => {
      setPreview(undefined);
      setPreview(await request<Preview>('/sync/preview', {}));
    })}>读取三方规则差异</button>
    {preview && <>
      <p role="status">{states[preview.status] ?? '版本状态需要进一步核对'}</p>
      <p className="muted">以下是本次取得的已提交规则记录。其他电脑继续修改后，请重新读取。原始材料、附件和审批历史不在本次预览中；这里暂不能批准或应用合并。</p>
      {preview.working_tree_dirty && <p className="warning">本机还有未提交的记录。这些内容未包含在下面的已提交版本中，合并前需要另行核对。</p>}
      {preview.staged_changes && <p className="warning">本机有已暂存、尚未提交的修改；预览没有更改这些修改。</p>}
      <details><summary>查看这次预览的版本依据</summary>
        <p>共同版本：{preview.base_commit}</p>
        <p>本机版本：{preview.local_commit}</p>
        <p>远端版本：{preview.remote_commit}</p>
        <p>预览校验值：{preview.preview_sha256}</p>
      </details>
      {preview.changes.length ? preview.changes.map(change => <article
        className="evidence" key={change.rule_id} aria-label={'规则差异 ' + change.rule_id}>
        <h4>{change.rule_id} · {changes[change.kind] ?? '记录需要核对'}</h4>
        <div className="sync-versions">
          <Version title="共同版本" snapshot={change.base} />
          <Version title="本机版本" snapshot={change.local} />
          <Version title="远端版本" snapshot={change.remote} />
        </div>
      </article>) : <p>本次未发现已提交规则记录的差异；其他资料没有纳入此预览。</p>}
    </>}
  </section>;
}
