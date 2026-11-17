import { useEffect, useState } from 'react';
import { request } from './api';
import type { Proposal, Rule } from './types';

type History = { snapshots: { commit: string; created_at: string; summary: string }[] };
type Preview = {
  target_commit: string;
  baseline_commit: string;
  changes: { rule_id: string; action: string; before: Rule | null; after: Rule }[];
};

export function Restore({ busy, run, open }: {
  busy: boolean;
  run: (task: () => Promise<void>) => void;
  open: (proposal: Proposal) => Promise<void>;
}) {
  const [history, setHistory] = useState<History>();
  const [target, setTarget] = useState('');
  const [preview, setPreview] = useState<Preview>();
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    void request<History>('/restore').then(value => {
      if (!cancelled) {
        setHistory(value);
        setTarget(value.snapshots[0]?.commit ?? '');
      }
    }).catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, []);
  return <section className="panel">
    <h2>恢复历史规则</h2>
    <p>先查看这次恢复涉及的规则，再创建提案并到审批中心明确批准。恢复会形成新版本，已有历史记录继续保留。</p>
    {error && <p role="alert">{error}</p>}
    {!history && !error && <p role="status">正在读取规则历史…</p>}
    {history && !history.snapshots.length && <p>尚无可恢复的规则历史。批准第一份规则后会出现记录。</p>}
    {!!history?.snapshots.length && <>
      <label htmlFor="restore-snapshot">选择规则历史版本</label>
      <select id="restore-snapshot" value={target} disabled={busy} onChange={e => {
        setTarget(e.target.value);
        setPreview(undefined);
      }}>{history.snapshots.map(s => <option key={s.commit} value={s.commit}>
        {s.created_at} · {s.commit.slice(0, 8)} · {s.summary}
      </option>)}</select>
      <button disabled={busy || !target} onClick={() => run(async () => {
        setPreview(await request<Preview>('/restore/preview', { commit: target }));
      })}>预览恢复内容</button>
    </>}
    {preview && <div>
      <h3>本次恢复涉及 {preview.changes.length} 条规则</h3>
      <p className="muted">当前仍未改变生效规则。以下为待审批内容；批准时将为受影响规则生成新版本。</p>
      {preview.changes.map(change => <article className="evidence" key={change.rule_id}>
        <h4>{change.rule_id} · {change.action === 'deactivate' ? '停用' : change.action === 'create' ? '恢复缺失规则' : '恢复历史内容'}</h4>
        <details open><summary>当前内容和恢复后内容</summary>
          <pre className="diff">{JSON.stringify({ before: change.before, after: change.after }, null, 2)}</pre>
        </details>
      </article>)}
      {!preview.changes.length && <p>当前规则与该历史版本一致，无需创建恢复提案。</p>}
      <button disabled={busy || !preview.changes.length} onClick={() => run(async () => {
        const plan = preview;
        setPreview(undefined);
        const proposal = await request<Proposal>('/restore', {
          commit: plan.target_commit,
          baseline_commit: plan.baseline_commit,
        });
        await open(proposal);
      })}>创建恢复提案并前往审批</button>
    </div>}
  </section>;
}
