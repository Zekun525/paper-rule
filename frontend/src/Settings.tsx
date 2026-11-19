import { useEffect, useState } from 'react';
import { request } from './api';
import { label } from './types';
import type { Proposal } from './types';
import { Restore } from './Restore';
import { SyncPreview } from './SyncPreview';

type Diagnostics = {
  status: string; version: string; memory_path: string;
  provider: { name: string; configured: boolean; connection: string; message: string };
  counts: { sources: number; feedback: number; rules: number; proposals: number; papers: number };
};
type Sync = {
  status: string; branch: string; commit: string; remote_configured: boolean;
  pending_commits: number | null; dirty: boolean;
};
type Props = { busy: boolean; run: (task: () => Promise<void>) => void; open: (proposal: Proposal) => Promise<void> };

export function Settings({ busy, run, open }: Props) {
  const [diagnostics, setDiagnostics] = useState<Diagnostics>();
  const [sync, setSync] = useState<Sync>();
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [difference, setDifference] = useState<string>();
  const [previewReset, setPreviewReset] = useState(0);
  const load = async () => {
    setPreviewReset(value => value + 1);
    setError('');
    const [a, b] = await Promise.all([
      request<Diagnostics>('/diagnostics'), request<Sync>('/sync'),
    ]);
    setDiagnostics(a); setSync(b);
  };
  useEffect(() => { void load().catch(e => setError(e.message)); }, []);
  const synchronize = (action: 'push' | 'pull') => run(async () => {
    setPreviewReset(value => value + 1);
    setMessage(''); setDifference(undefined);
    const result = await request<{ status: string }>('/sync/' + action, {});
    const messages: Record<string, string> = {
      synced: '此次同步已完成。',
      local: '尚未配置私有远端，资料继续保存在本机。',
      pending: '此次同步未完成，本机已批准的规则仍然保留。网络恢复后可以重试。',
      conflict: '本机与远端需要进一步核对，或本机仍有未提交的记录。请先查看差异；系统不会强制覆盖远端。',
    };
    setMessage(messages[result.status] ?? '此次同步尚未确认完成，请刷新状态后检查。');
    await load();
  });
  return <div className="page-grid">
    <Restore busy={busy} run={run} open={open} />
    <section className="panel">
      <h2>本地服务与 AI 配置</h2>
      {error && <p role="alert">{error}</p>}
      <button disabled={busy} onClick={() => run(load)}>重新检查状态</button>
      {!diagnostics && !error && <p role="status">正在读取本地状态…</p>}
      {diagnostics && <>
        <p>服务：{diagnostics.status === 'ok' ? '正常运行' : '需要检查'} · 版本 {diagnostics.version}</p>
        <p>私有记忆位置：{diagnostics.memory_path}</p>
        <p>{diagnostics.counts.sources} 份来源 · {diagnostics.counts.feedback} 条意见 · {diagnostics.counts.rules} 条规则 · {diagnostics.counts.papers} 份论文档案</p>
        <h3>AI 服务</h3>
        <p>当前模式：{diagnostics.provider.name === 'manual' ? '人工编辑' : diagnostics.provider.name}</p>
        <p>{diagnostics.provider.message}</p>
        <p className="muted">配置检测不会向模型发送材料。讨论中出现服务不可用时，意见和草稿仍会保存；只有明确批准才改变生效规则。</p>
      </>}
    </section>
    <section className="panel sync-panel">
      <h2>私有记忆同步</h2>
      {sync && <>
        <p>状态：{label(sync.status)}</p>
        <p>私有远端：{sync.remote_configured ? '已配置' : '尚未配置，仅在本机保存'}</p>
        <p>当前分支：{sync.branch || '未命名'}</p>
        <p>规则快照：{sync.commit || '尚无提交'}</p>
        <p>待同步提交：{sync.pending_commits ?? '尚无可比较的上游分支'}</p>
        {sync.dirty && <p className="warning">本机有尚未提交的记录，拉取更新可能被暂缓，以免覆盖这些记录。</p>}
        <div className="actions">
          <button disabled={busy || !sync.remote_configured} onClick={() => synchronize('push')}>推送已批准记录</button>
          <button disabled={busy || !sync.remote_configured} onClick={() => synchronize('pull')}>拉取私有记忆更新</button>
          <button disabled={busy || !sync.remote_configured} onClick={() => run(async () => {
            const result = await request<{ diff: string }>('/sync/differences');
            setDifference(result.diff);
          })}>查看本机与远端差异</button>
        </div>
        {!sync.remote_configured && <p className="muted">需要跨电脑使用时，请按安装指南为这份记忆配置私有仓库。公开程序仓库不用于保存个人意见和论文材料。</p>}
      </>}
      {message && <p role="status">{message}</p>}
      {difference !== undefined && <details open>
        <summary>规则差异</summary>
        {difference ? <pre className="diff">{difference}</pre>
          : <p>本次未返回规则差异；请结合同步状态判断是否已经取得远端版本。</p>}
      </details>}
      <SyncPreview busy={busy} remoteConfigured={!!sync?.remote_configured}
        resetToken={previewReset} run={run} />
    </section>
  </div>;
}
