import { useState } from 'react';
import { encodeFile, request } from './api';
import type { Feedback, Paper, Rule, Source } from './types';
import { label } from './types';
import { RuleEditor } from './RuleEditor';
import { OneOffDraft } from './OneOffDraft';
import { FeedbackAnalysis } from './FeedbackAnalysis';
import { RevisionPairEvidence, RevisionPairImport, sourceRoleLabel } from './RevisionPairs';
import { classifications, currentClassification, FeedbackCorrection, SourceTranscription } from './FeedbackEvidence';

export function Sources({ sources, feedback, papers, reload, create, run, busy }: { sources: Source[]; feedback: Feedback[]; papers: Paper[]; reload: () => Promise<void>; create: (rule: Rule, operation?: string) => Promise<void>; run: (task: () => Promise<void>) => void; busy: boolean }) {
  const [reviewer, setReviewer] = useState('author'), [role, setRole] = useState('author'), [paper, setPaper] = useState(''), [kind, setKind] = useState('text'), [intent, setIntent] = useState(''), [text, setText] = useState(''), [selected, setSelected] = useState(''), [draft, setDraft] = useState<Rule>(), [filter, setFilter] = useState('');
  const [date, setDate] = useState('');
  const [importNotice, setImportNotice] = useState('');
  const upload = async (files: File[]) => {
    setImportNotice('');
    let imported = 0;
    let count = 0;
    try {
      for (const file of files) {
        const result = await request<{ source: Source; feedback: Feedback[] }>('/sources', {
          filename: file.name, content_base64: await encodeFile(file), reviewer_id: reviewer,
          reviewer_role: role, paper_id: paper || null, kind, intent, date,
        });
        imported += 1;
        count += result.feedback.length;
        setSelected(result.source.id);
        setFilter('');
      }
    } finally {
      if (imported) {
        setImportNotice(`已保存 ${imported} 份材料。${count ? `提取了 ${count} 条意见，点选来源可查看原话。` : '未提取到意见，可以手动补录。'}`);
        await reload();
      }
    }
  };
  const selectedSource = sources.find(source => source.id === selected);
  return <div className="page-grid"><section className="panel"><h2>导入意见和材料</h2><div className="editor">
    <label>也可以直接粘贴意见<textarea rows={5} placeholder="例如：在使用关键假设之前，先解释它为什么成立。" value={text} onChange={e => setText(e.target.value)} /></label>
    <button className="primary" disabled={busy || !text.trim()} onClick={() => run(async () => { await upload([new File([text], 'pasted-feedback.txt', { type: 'text/plain' })]); setText(''); })}>保存粘贴意见</button>
    <p className="muted">保存后可在右侧查看原话，再决定是否创建规则提案。</p>
    <details><summary>填写来源、论文和日期（可选）</summary>
    <label>来源代号<input value={reviewer} required onChange={e => setReviewer(e.target.value)} /></label><label>来源角色<select value={role} onChange={e => setRole(e.target.value)}><option value="author">本人</option><option value="advisor">导师</option><option value="collaborator">合作者</option><option value="senior">师兄 / 师姐</option><option value="other">其他</option></select></label>
    <label>关联论文<select value={paper} onChange={e => setPaper(e.target.value)}><option value="">暂不关联</option>{papers.map(p => <option key={p.paper_id} value={p.paper_id}>{p.title || p.paper_id}</option>)}</select></label>
    <label>用途<select value={kind} onChange={e => setKind(e.target.value)}><option value="text">修改意见</option><option value="annotated_pdf">PDF 批注</option><option value="exemplar">学习范文</option><option value="meeting_notes">会议记录</option><option value="docx">Word 文档</option></select></label><label>学习目标 / 来源说明<input value={intent} onChange={e => setIntent(e.target.value)} /></label>
    <label>材料日期<input type="date" value={date} onChange={event => setDate(event.target.value)} /></label>
    </details>
    <label className="dropzone" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) run(() => upload(Array.from(e.dataTransfer.files))); }}>选择或拖入多个文件<input aria-label="上传材料" disabled={busy} type="file" multiple accept=".txt,.md,.tex,.pdf,.docx" onChange={e => { const files = Array.from(e.target.files ?? []); run(() => upload(files)); e.currentTarget.value = ''; }} /></label>
    {importNotice && <p className="notice" role="status">{importNotice}</p>}
    <RevisionPairImport reviewer={reviewer} role={role} paper={paper} intent={intent}
      date={date} busy={busy} reload={reload} run={run} onImported={setSelected} />
  </div><h2>来源档案（{sources.length}）</h2>{sources.map(s => <button key={s.id} className={'record ' + (selected === s.id ? 'chosen' : '')} onClick={() => setSelected(s.id)}><b>{s.filename}</b><small>{label(s.extraction_status)} · {s.reviewer_id}</small>{s.warnings.map((w, i) => <p key={i}>{w}</p>)}</button>)}{!sources.length && <p className="empty">还没有材料。导入后会保留原件和提取结果。</p>}</section>
    <section className="panel">
      <h2>原始意见与依据</h2>
      {selectedSource && <p className="muted">
        来源：{selectedSource.reviewer_id} · {sourceRoleLabel(selectedSource.reviewer_role)} ·
        材料日期：{selectedSource.date || '未记录'}
      </p>}
      {selectedSource?.kind === 'revision_pair' &&
        <RevisionPairEvidence key={selectedSource.id} sourceId={selectedSource.id} />}
      {selectedSource && selectedSource.kind !== 'revision_pair' &&
        <SourceTranscription key={selectedSource.id} source={selectedSource}
        busy={busy} reload={reload} run={run} />}
      <label>筛选意见<input placeholder="搜索原话、来源代号或论文" value={filter}
        onChange={event => setFilter(event.target.value)} /></label>
      {selected && <button onClick={() => setSelected('')}>显示全部来源</button>}
      {feedback.filter(item => (!selected || item.source_id === selected) &&
        (item.quote + item.corrections.map(entry => entry.text).join(' ') +
          item.reviewer_id + (item.paper_id ?? '')).includes(filter)).map(item => {
        const classification = currentClassification(item);
        const oneOff = classification === 'one_off_edit';
        return <article className="evidence" key={item.id}>
          <small>{item.id} · {item.reviewer_id} · {item.location.page ?
            '第 ' + item.location.page + ' 页' : item.location.section || '定位待确认'}</small>
          {item.extraction_method === 'manual_transcription' && <p>人工补录内容</p>}
          <blockquote>{item.quote || '此标注没有文字说明，请补充其意图。'}</blockquote>
          <p>当前确认分类：{classifications[classification] ?? classification}</p>
          {item.corrections.map((entry, index) => <article key={index}>
            <p>补充：{entry.text}（{entry.reason}）</p>
            {entry.classification && <small>
              补充确认分类：{classifications[entry.classification] ?? entry.classification}
            </small>}
          </article>)}
          <FeedbackCorrection item={item} busy={busy} reload={reload} run={run} />
          <FeedbackAnalysis key={item.id + item.sha256} item={item}
            busy={busy} run={run} draft={setDraft} />
          {oneOff && <p>此意见已确认是一次性修改，不会据此创建长期规则。</p>}
          {oneOff && <OneOffDraft key={item.sha256} item={item} papers={papers}
            busy={busy} create={create} run={run} />}
          <button disabled={busy || oneOff} onClick={() => setDraft({
            id: 'R-' + crypto.randomUUID().slice(0, 8), version: 1, status: 'proposed',
            short_title: '', statement: item.corrections.at(-1)?.text || item.quote,
            source_feedback_ids: [item.id],
            scope: { levels: item.paper_id ? ['paper'] : ['global'],
              paper_ids: item.paper_id ? [item.paper_id] : [] },
          })}>据此创建提案</button>
          {sources.find(source => source.id === item.source_id)?.filename.toLowerCase()
            .endsWith('.pdf') && item.location.page_index != null && <details>
            <summary>查看原页</summary>
            <img className="pdf-preview" alt="意见所在 PDF 页面" loading="lazy"
              src={'/api/sources/' + item.source_id + '/preview/' + item.location.page_index} />
          </details>}
        </article>;
      })}
      {!feedback.length && <p className="empty">
        请在左侧选择材料进行人工补录，或导入材料后核对原话、定位和来源。
      </p>}
    </section>
    {draft && <section className="panel"><h2>从意见整理规则</h2><RuleEditor key={draft.id} initial={draft} busy={busy} save={rule => run(async () => { await create(rule); setDraft(undefined); })} /><button onClick={() => setDraft(undefined)}>取消编辑</button></section>}
  </div>;
}
