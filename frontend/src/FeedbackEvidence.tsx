import { useEffect, useState } from 'react';
import { request } from './api';
import type { Feedback, Source } from './types';

type Actions = {
  busy: boolean;
  reload: () => Promise<void>;
  run: (task: () => Promise<void>) => void;
};

export const classifications: Record<string, string> = {
  clarification_needed: '待澄清',
  one_off_edit: '当前论文的一次性修改',
  reusable_rule: '可复用写作规范',
  paper_specific_rule: '仅适用于特定论文的要求',
  exemplar: '正面写作范例',
  negative_example: '问题写法案例',
  research_fact: '论文事实或研究主张',
};

export function currentClassification(item: Feedback): string {
  return [...item.corrections].reverse().find(entry => entry.classification)?.classification
    || item.classification;
}

export function SourceTranscription({ source, busy, reload, run }: Actions & { source: Source }) {
  const [text, setText] = useState('');
  const [reason, setReason] = useState('');
  const [role, setRole] = useState('');
  const [classification, setClassification] = useState('clarification_needed');
  const [page, setPage] = useState('');
  const [section, setSection] = useState('');
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const [message, setMessage] = useState('');
  useEffect(() => {
    setRequestId(crypto.randomUUID());
  }, [text, reason, role, classification, page, section]);
  const prefix = 'transcription-' + source.id;
  return <section aria-label="原件人工补录">
    <h3>为 {source.filename} 人工补录</h3>
    <p>来源代号：{source.reviewer_id}。请核对原件后填写；补录不会改变原提取状态，也不会自动批准规则。</p>
    <form onSubmit={event => {
      event.preventDefault();
      setMessage('');
      run(async () => {
        await request('/sources/' + source.id + '/transcriptions', {
          request_id: requestId, text, reason, reviewer_role: role, classification,
          page: page ? Number(page) : null, section,
        });
        await reload();
        setText(''); setReason(''); setRequestId(crypto.randomUUID());
        setMessage('已保存人工补录，原件和提取状态均保留。');
      });
    }}>
      <label htmlFor={prefix + '-text'}>补录原文</label>
      <textarea id={prefix + '-text'} required maxLength={100000} rows={4}
        value={text} onChange={event => setText(event.target.value)} />
      <label htmlFor={prefix + '-reason'}>补录原因</label>
      <input id={prefix + '-reason'} required maxLength={2000}
        value={reason} onChange={event => setReason(event.target.value)} />
      <label htmlFor={prefix + '-role'}>确认来源角色</label>
      <input id={prefix + '-role'} required maxLength={100} placeholder="例如 advisor、collaborator 或自定义角色"
        value={role} onChange={event => setRole(event.target.value)} />
      <label htmlFor={prefix + '-classification'}>补录内容分类</label>
      <select id={prefix + '-classification'} value={classification}
        onChange={event => setClassification(event.target.value)}>
        {Object.entries(classifications).map(([value, title]) =>
          <option key={value} value={value}>{title}</option>)}
      </select>
      {source.filename.toLowerCase().endsWith('.pdf') && <>
        <label htmlFor={prefix + '-page'}>原件页码（未知可留空）</label>
        <input id={prefix + '-page'} type="number" min={1} step={1}
          value={page} onChange={event => setPage(event.target.value)} />
      </>}
      <label htmlFor={prefix + '-section'}>章节或位置说明</label>
      <input id={prefix + '-section'} maxLength={300}
        value={section} onChange={event => setSection(event.target.value)} />
      <button disabled={busy || !text.trim() || !reason.trim() || !role.trim()}>
        保存人工补录
      </button>
    </form>
    {message && <p role="status">{message}</p>}
  </section>;
}

export function FeedbackCorrection({ item, busy, reload, run }: Actions & { item: Feedback }) {
  const [text, setText] = useState('');
  const [reason, setReason] = useState('');
  const [classification, setClassification] = useState('');
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const [message, setMessage] = useState('');
  useEffect(() => {
    setRequestId(crypto.randomUUID());
  }, [text, reason, classification, item.sha256]);
  const prefix = 'correction-' + item.id;
  return <details>
    <summary>补充解释或纠错</summary>
    <p>原话保持不变。新解释会追加保存；重新分类不会直接修改任何生效规则。</p>
    <form onSubmit={event => {
      event.preventDefault();
      setMessage('');
      run(async () => {
        await request('/feedback/' + item.id + '/corrections', {
          request_id: requestId, expected_sha256: item.sha256,
          text, reason, classification: classification || null,
        });
        await reload();
        setText(''); setReason(''); setClassification('');
        setRequestId(crypto.randomUUID());
        setMessage('已追加纠错记录，原话和生效规则均未改动。');
      });
    }}>
      <label htmlFor={prefix + '-text'}>修正或补充的解释</label>
      <textarea id={prefix + '-text'} required maxLength={100000} rows={3}
        value={text} onChange={event => setText(event.target.value)} />
      <label htmlFor={prefix + '-reason'}>修正依据</label>
      <input id={prefix + '-reason'} required maxLength={2000}
        value={reason} onChange={event => setReason(event.target.value)} />
      <label htmlFor={prefix + '-classification'}>补充确认分类</label>
      <select id={prefix + '-classification'} value={classification}
        onChange={event => setClassification(event.target.value)}>
        <option value="">保留目前分类</option>
        {Object.entries(classifications).map(([value, title]) =>
          <option key={value} value={value}>{title}</option>)}
      </select>
      <button disabled={busy || !text.trim() || !reason.trim()}>追加纠错记录</button>
    </form>
    {message && <p role="status">{message}</p>}
  </details>;
}
