import { useEffect, useState } from 'react';
import { encodeFile, request } from './api';
import type { Source } from './types';

type RevisionPairResult = {
  diff_source: string; diff: string; text_changed: boolean; originals: Source[];
};

export function sourceRoleLabel(value?: string): string {
  const roles: Record<string, string> = {
    author: '本人', advisor: '导师', collaborator: '合作者',
    senior: '师兄 / 师姐', other: '其他',
  };
  return value ? roles[value] || value : '未记录角色';
}

type ImportProps = {
  reviewer: string; role: string; paper: string; intent: string; date: string;
  busy: boolean; reload: () => Promise<void>;
  run: (task: () => Promise<void>) => void; onImported: (sourceId: string) => void;
};

export function RevisionPairImport({
  reviewer, role, paper, intent, date, busy, reload, run, onImported,
}: ImportProps) {
  const [before, setBefore] = useState<File>();
  const [after, setAfter] = useState<File>();
  const [generation, setGeneration] = useState(0);
  const [message, setMessage] = useState('');
  return <details>
    <summary>导入修改前后对照</summary>
    <section aria-label="修改前后对照导入">
      <p>选择修改前、修改后的两份同格式文件。支持 LaTeX、Markdown、TXT 和 DOCX，每份最多 25 MiB。</p>
      <p>沿用上方填写的来源、角色、论文、说明和材料日期。保存原件与差异后，仍需核对修改意图。</p>
      <form onSubmit={event => {
        event.preventDefault();
        const beforeFile = before, afterFile = after;
        if (!beforeFile || !afterFile) return;
        setMessage('');
        run(async () => {
          const suffix = (file: File) => file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
          if (!['.tex', '.md', '.txt', '.docx'].includes(suffix(beforeFile)) ||
            suffix(beforeFile) !== suffix(afterFile)) {
            throw new Error('请选择两份相同格式的 LaTeX、Markdown、TXT 或 DOCX 文件。');
          }
          const result = await request<RevisionPairResult>('/revision-pairs', {
            before_filename: beforeFile.name, after_filename: afterFile.name,
            before_content_base64: await encodeFile(beforeFile),
            after_content_base64: await encodeFile(afterFile),
            reviewer_id: reviewer, reviewer_role: role, paper_id: paper || null, intent, date,
          });
          await reload();
          onImported(result.diff_source);
          setBefore(undefined); setAfter(undefined);
          setGeneration(value => value + 1);
          setMessage('已保存原稿、修订稿和差异；没有自动建立规则。');
        });
      }}>
        <div key={generation}>
          <label>修改前文件<input type="file" required disabled={busy}
            accept=".tex,.md,.txt,.docx"
            onChange={event => setBefore(event.target.files?.[0])} /></label>
          <label>修改后文件<input type="file" required disabled={busy}
            accept=".tex,.md,.txt,.docx"
            onChange={event => setAfter(event.target.files?.[0])} /></label>
        </div>
        <button disabled={busy || !before || !after || !reviewer.trim()}>保存并查看差异</button>
      </form>
      {message && <p role="status">{message}</p>}
    </section>
  </details>;
}

export function RevisionPairEvidence({ sourceId }: { sourceId: string }) {
  const [data, setData] = useState<RevisionPairResult>();
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setData(undefined); setError('');
    void request<RevisionPairResult>('/revision-pairs/' + encodeURIComponent(sourceId))
      .then(result => { if (active) setData(result); })
      .catch(reason => {
        if (active) setError(reason instanceof Error ? reason.message : '无法读取对照依据。');
      });
    return () => { active = false; };
  }, [sourceId]);
  return <section aria-label="修改前后差异依据">
    <h3>修改前后对照</h3>
    {error && <p role="alert">无法核验这份对照：{error}。请核对保留的原件。</p>}
    {!data && !error && <p role="status">正在核对原件与差异…</p>}
    {data && <>
      <p>两份原件与差异已关联保存。本次读取已核对保存的文件哈希；这些材料仍需人工确认，不代表已批准规则。</p>
      {data.originals.map((original, index) => <article key={original.id}>
        <h4>{index === 0 ? '修改前：' : '修改后：'}{original.filename}</h4>
        <p>{original.reviewer_id} · {sourceRoleLabel(original.reviewer_role)} · {original.date || '未记录日期'}</p>
        <details>
          <summary>原件来源与哈希</summary>
          <p>来源：{original.id}</p>
          <code>{original.sha256}</code>
          {original.paper_id && <p>关联论文：{original.paper_id}</p>}
          {original.intent && <p>来源说明：{original.intent}</p>}
        </details>
        {original.warnings.map((warning, position) =>
          <p className="warning" key={position}>{warning}</p>)}
      </article>)}
      <pre className="diff" aria-label="修改前后差异">{data.diff ||
        '未发现按行比较的文字差异；两份原件及哈希仍已保存。'}</pre>
    </>}
  </section>;
}
