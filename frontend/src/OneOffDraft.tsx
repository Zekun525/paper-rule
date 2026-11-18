import { useState } from 'react';
import type { Feedback, Paper, Rule } from './types';

type Props = {
  item: Feedback; papers: Paper[]; busy: boolean;
  create: (rule: Rule, operation?: string) => Promise<void>;
  run: (task: () => Promise<void>) => void;
};

export function OneOffDraft({ item, papers, busy, create, run }: Props) {
  const choices = papers.filter(paper => !item.paper_id || paper.paper_id === item.paper_id);
  const [paperId, setPaperId] = useState(item.paper_id && choices.length ? item.paper_id : '');
  const [title, setTitle] = useState('');
  const [instruction, setInstruction] = useState(item.corrections.at(-1)?.text || item.quote);
  const prefix = 'one-off-' + item.id;
  return <details>
    <summary>整理为论文修改任务</summary>
    <p>请确认这次要改什么。保存后会打开审批中心，明确批准后才保存为任务。</p>
    {!choices.length && <p>请先在论文工作区为{item.paper_id || '目标论文'}建立档案，再创建任务。</p>}
    <form onSubmit={event => {
      event.preventDefault();
      run(async () => {
        await create({
          id: 'TASK-' + crypto.randomUUID().slice(0, 8), version: 1, status: 'proposed',
          short_title: title.trim(), statement: instruction.trim(), check_method: 'manual',
          source_feedback_ids: [item.id],
          scope: { levels: ['paper'], paper_ids: [paperId] },
        }, 'one_off');
      });
    }}>
      <label htmlFor={prefix + '-paper'}>任务所属论文</label>
      <select id={prefix + '-paper'} required value={paperId} disabled={busy}
        onChange={event => setPaperId(event.target.value)}>
        <option value="">请选择已保存的论文</option>
        {choices.map(paper => <option key={paper.paper_id} value={paper.paper_id}>
          {paper.title || paper.paper_id}
        </option>)}
      </select>
      <label htmlFor={prefix + '-title'}>任务标题</label>
      <input id={prefix + '-title'} required maxLength={300} value={title} disabled={busy}
        onChange={event => setTitle(event.target.value)} />
      <label htmlFor={prefix + '-instruction'}>任务修改内容</label>
      <textarea id={prefix + '-instruction'} required maxLength={100000} rows={4}
        value={instruction} disabled={busy} onChange={event => setInstruction(event.target.value)} />
      <button disabled={busy || !paperId || !title.trim() || !instruction.trim()}>
        保存任务提案
      </button>
    </form>
  </details>;
}
