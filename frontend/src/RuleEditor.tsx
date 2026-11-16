import { useId, useState } from 'react';
import type { Rule } from './types';

export function RuleEditor({ initial, save, busy }: { initial?: Rule; save: (rule: Rule) => void; busy: boolean }) {
  const formId = useId();
  const [rule, setRule] = useState<Rule>(initial ?? { id: 'R-' + crypto.randomUUID().slice(0, 8), version: 1, status: 'proposed', short_title: '', statement: '', scope: { levels: ['global'] }, check_method: 'semantic' });
  return <form className="editor" onSubmit={e => { e.preventDefault(); save(rule); }}>
    <label>规则编号<input required value={rule.id} disabled={!!initial} onChange={e => setRule({ ...rule, id: e.target.value })} pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,100}" /></label>
    <label>标题<input required value={rule.short_title} onChange={e => setRule({ ...rule, short_title: e.target.value })} /></label>
    <label htmlFor={formId + '-statement'}>规则内容</label><textarea id={formId + '-statement'} required rows={4} value={rule.statement} onChange={e => setRule({ ...rule, statement: e.target.value })} />
    <label>适用层级<select value={rule.scope.levels.at(-1)} onChange={e => setRule({ ...rule, scope: { ...rule.scope, levels: [e.target.value] } })}><option value="global">全局</option><option value="research_type">研究类型</option><option value="publication">投稿期刊和文章类型</option><option value="paper">指定论文</option><option value="section_task">章节与任务</option></select></label>
    {(['paper_ids', 'sections', 'venues', 'article_types', 'exceptions'] as const).map((key, i) => <label key={key}>{['论文编号', '章节', '期刊', '文章类型', '例外说明'][i]}（逗号分隔）<input value={(rule.scope[key] ?? []).join(', ')} onChange={e => setRule({ ...rule, scope: { ...rule.scope, [key]: e.target.value.split(',').map(s => s.trim()).filter(Boolean) } })} /></label>)}
    <label>检查方式<select value={rule.check_method ?? 'semantic'} onChange={e => setRule({ ...rule, check_method: e.target.value })}><option value="semantic">AI 语义审查</option><option value="deterministic">固定词句检查（内容使用 avoid: 开头）</option></select></label>
    <label htmlFor={formId + '-positive'}>正面案例</label><textarea id={formId + '-positive'} value={rule.positive_example ?? ''} onChange={e => setRule({ ...rule, positive_example: e.target.value })} />
    <label htmlFor={formId + '-negative'}>问题案例</label><textarea id={formId + '-negative'} value={rule.negative_example ?? ''} onChange={e => setRule({ ...rule, negative_example: e.target.value })} />
    <p className="muted">保存只更新待审批提案。生效规则必须另外明确批准。</p><button disabled={busy} className="primary">保存待审批版本</button>
  </form>;
}
