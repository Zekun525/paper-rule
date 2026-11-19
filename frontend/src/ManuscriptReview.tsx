import { useEffect, useState } from 'react';
import { request } from './api';

type Props = {
  paperId: string;
  busy: boolean;
  run: (task: () => Promise<void>) => void;
  onSaved: (reviewId: string) => Promise<void>;
};

export function ManuscriptReview({ paperId, busy, run, onSaved }: Props) {
  const [mode, setMode] = useState<'text' | 'diff'>('text');
  const [filename, setFilename] = useState('manuscript.tex');
  const [text, setText] = useState('');
  const [section, setSection] = useState('');
  const [task, setTask] = useState('');
  const [semantic, setSemantic] = useState(false);
  const [maxCalls, setMaxCalls] = useState(8);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setMode('text'); setFilename('manuscript.tex'); setText('');
    setSection(''); setTask(''); setSemantic(false); setMaxCalls(8); setSaved(false);
  }, [paperId]);

  return <section aria-label="发起论文审查">
    <h3>发起论文审查</h3>
    <p className="muted">检查当前论文适用的已批准规则。审查报告保存到私有记忆；审查不会修改稿件或批准规则。</p>
    <form onSubmit={event => {
      event.preventDefault(); setSaved(false);
      run(async () => {
        const report = await request<{ review_id: string }>('/reviews/check', {
          paper_id: paperId, mode, filename, text: mode === 'text' ? text : '',
          section, task, semantic, send_to_provider: semantic, max_semantic_calls: maxCalls,
        });
        await onSaved(report.review_id);
        setSaved(true);
      });
    }}>
      <label htmlFor="manuscript-review-mode">审查范围</label>
      <select id="manuscript-review-mode" value={mode} disabled={busy}
        onChange={event => {
          setMode(event.target.value as 'text' | 'diff'); setSaved(false);
        }}>
        <option value="text">提供的稿件全文或片段</option>
        <option value="diff">已登记论文项目中的 Git 变更</option>
      </select>
      {mode === 'text' ? <>
        <label htmlFor="manuscript-review-file">选择 UTF-8 文本文件（可选）</label>
        <input id="manuscript-review-file" type="file" key={paperId + mode}
          accept=".tex,.bib,.md,.txt" disabled={busy}
          onChange={event => {
            const file = event.target.files?.[0];
            if (!file) return;
            run(async () => {
              if (file.size > 400000) {
                throw new Error('稿件超过本次审查的长度上限，请按章节拆分后审查。');
              }
              let content: string;
              try { content = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer()); }
              catch { throw new Error('文件不是有效的 UTF-8 文本，请另存为 UTF-8 后重试。'); }
              if (content.length > 100000) {
                throw new Error('每次最多审查 100000 个字符，请按章节拆分。');
              }
              setFilename(file.name); setText(content); setSaved(false);
            });
          }} />
        <label htmlFor="manuscript-review-filename">稿件文件名</label>
        <input id="manuscript-review-filename" value={filename} required maxLength={240}
          disabled={busy} onChange={event => { setFilename(event.target.value); setSaved(false); }} />
        <label htmlFor="manuscript-review-text">稿件原文</label>
        <textarea id="manuscript-review-text" value={text} rows={10} required
          maxLength={100000} disabled={busy}
          onChange={event => { setText(event.target.value); setSaved(false); }} />
        <p className="muted">仅审查这里提供的内容。文件名用于报告定位，不会据此读取电脑上的其他文件。</p>
      </> : <p className="muted">读取论文档案中已保存的项目路径，比较当前文件与 HEAD；包括尚未跟踪的文本文件。请先保存论文项目路径。启用 AI 时，会提供所选文件的全文作为变更行的判断上下文。</p>}
      <label htmlFor="manuscript-review-section">本次审查章节</label>
      <input id="manuscript-review-section" value={section} maxLength={500} disabled={busy}
        placeholder="例如 introduction 或 proof"
        onChange={event => { setSection(event.target.value); setSaved(false); }} />
      <label htmlFor="manuscript-review-task">本次审查任务</label>
      <input id="manuscript-review-task" value={task} maxLength={2000} disabled={busy}
        placeholder="例如 proof_rewrite"
        onChange={event => { setTask(event.target.value); setSaved(false); }} />
      <label className="inline-consent" htmlFor="manuscript-review-ai">
        <input id="manuscript-review-ai" type="checkbox" checked={semantic} disabled={busy}
          onChange={event => { setSemantic(event.target.checked); setSaved(false); }} />
        使用已配置的 AI 服务审查，并同意发送本次稿件上下文及适用规则
      </label>
      <p className="muted">未勾选时只执行本地确定性检查。AI 审查按“文件 × 规则”分别请求，可能产生服务费用；无效响应、无法判断和未执行的部分都会保留未完成状态。</p>
      {semantic && <>
        <label htmlFor="manuscript-review-budget">最多 AI 请求次数</label>
        <input id="manuscript-review-budget" type="number" min={1} max={32} step={1}
          required value={maxCalls} disabled={busy}
          onChange={event => { setMaxCalls(Number(event.target.value)); setSaved(false); }} />
      </>}
      <button className="primary" disabled={busy || !paperId || (mode === 'text' && !text.trim())}>
        {busy ? '正在处理，请稍候…' : '开始审查并保存报告'}
      </button>
    </form>
    {saved && <p role="status">审查报告已保存，请核对逐条检查结果和待人工确认的问题。生效规则没有改变。</p>}
  </section>;
}
