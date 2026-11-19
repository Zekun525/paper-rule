import { useEffect, useId, useRef, useState } from 'react';
import type { Rule } from './types';
import { RuleRelationsEditor } from './RuleRelationsEditor';
import { ScopeFiltersEditor } from './ScopeFiltersEditor';

function ScopeValues({ label, values, change, busy, multiline = false }: {
  label: string; values: string[]; change: (values: string[]) => void;
  busy: boolean; multiline?: boolean;
}) {
  const separator = multiline ? '\n' : ', ';
  const serialized = JSON.stringify(values);
  const [text, setText] = useState(values.join(separator));
  const seen = useRef(serialized);
  const emitted = useRef(serialized);
  useEffect(() => {
    if (serialized !== seen.current) {
      seen.current = serialized;
      if (serialized !== emitted.current) {
        emitted.current = serialized;
        setText(values.join(separator));
      }
    }
  }, [serialized, values, separator]);
  function update(value: string) {
    setText(value);
    const parsed = value.split(multiline ? '\n' : ',').map(item => item.trim()).filter(Boolean);
    emitted.current = JSON.stringify(parsed);
    change(parsed);
  }
  return <label>{label}{multiline
    ? <textarea rows={3} disabled={busy} value={text}
      onChange={event => update(event.target.value)} />
    : <input disabled={busy} value={text} onChange={event => update(event.target.value)} />}
  </label>;
}

function localDateTime(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (number: number) => String(number).padStart(2, '0');
  return String(date.getFullYear()).padStart(4, '0') + '-' + pad(date.getMonth() + 1)
    + '-' + pad(date.getDate()) + 'T' + pad(date.getHours()) + ':' + pad(date.getMinutes());
}

export function RuleEditor({ initial, save, busy }: { initial?: Rule; save: (rule: Rule) => void; busy: boolean }) {
  const formId = useId();
  const [rule, setRule] = useState<Rule>(initial ?? { id: 'R-' + crypto.randomUUID().slice(0, 8), version: 1, status: 'proposed', short_title: '', statement: '', scope: { levels: ['global'] }, check_method: 'semantic' });
  return <form className="editor" onSubmit={e => { e.preventDefault(); save(rule); }}>
    <label>规则编号<input required value={rule.id} disabled={!!initial} onChange={e => setRule({ ...rule, id: e.target.value })} pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,100}" /></label>
    <label>标题<input required value={rule.short_title} onChange={e => setRule({ ...rule, short_title: e.target.value })} /></label>
    <label htmlFor={formId + '-statement'}>规则内容</label><textarea id={formId + '-statement'} required rows={4} value={rule.statement} onChange={e => setRule({ ...rule, statement: e.target.value })} />
    <label>适用层级<select value={rule.scope.levels.at(-1)} onChange={e => setRule({ ...rule, scope: { ...rule.scope, levels: [e.target.value] } })}><option value="global">全局</option><option value="research_type">研究类型</option><option value="publication">投稿期刊和文章类型</option><option value="paper">指定论文</option><option value="section_task">章节与任务</option></select></label>
    {([
      ['paper_ids', '论文编号'], ['research_types', '研究类型'], ['sections', '章节'],
      ['venues', '期刊'], ['article_types', '文章类型'], ['task_types', '任务类型'],
    ] as const).map(([key, label]) => <ScopeValues key={key}
      label={label + '（逗号分隔）'} values={rule.scope[key] ?? []} busy={busy}
      change={values => setRule(current => ({
        ...current, scope: { ...current.scope, [key]: values },
      }))} />)}
    <ScopeFiltersEditor kind="include" entries={rule.scope.include ?? []} busy={busy}
      change={entries => setRule(current => ({
        ...current, scope: { ...current.scope, include: entries },
      }))} />
    <ScopeFiltersEditor kind="exclude" entries={rule.scope.exclude ?? []} busy={busy}
      change={entries => setRule(current => ({
        ...current, scope: { ...current.scope, exclude: entries },
      }))} />
    <ScopeValues label="例外说明（每行一条）" values={rule.scope.exceptions ?? []}
      busy={busy} multiline change={values => setRule(current => ({
        ...current, scope: { ...current.scope, exceptions: values },
      }))} />
    <p className="muted">例外说明会随规则一起保存，判断是否适用仍需语义审查或人工核对。</p>
    <label>生效时间（本地时间）<input type="datetime-local" disabled={busy}
      min="0001-01-01T00:00" max="9999-12-31T23:59"
      value={localDateTime(rule.scope.effective_from)}
      onChange={event => {
        const value = event.target.value ? new Date(event.target.value).toISOString() : null;
        setRule(current => ({ ...current, scope: { ...current.scope, effective_from: value } }));
      }} /></label>
    <label>检查方式<select value={rule.check_method ?? 'semantic'} onChange={e => setRule({ ...rule, check_method: e.target.value })}><option value="semantic">AI 语义审查</option><option value="deterministic">固定词句检查（内容使用 avoid: 开头）</option></select></label>
    <RuleRelationsEditor relations={rule.relations} busy={busy}
      change={relations => setRule(current => ({ ...current, relations }))} />
    <label htmlFor={formId + '-positive'}>正面案例</label><textarea id={formId + '-positive'} value={rule.positive_example ?? ''} onChange={e => setRule({ ...rule, positive_example: e.target.value })} />
    <label htmlFor={formId + '-negative'}>问题案例</label><textarea id={formId + '-negative'} value={rule.negative_example ?? ''} onChange={e => setRule({ ...rule, negative_example: e.target.value })} />
    <p className="muted">保存只更新待审批提案。生效规则必须另外明确批准。</p><button disabled={busy} className="primary">保存待审批版本</button>
  </form>;
}
