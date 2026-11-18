import { useId } from 'react';
import type { RuleRelation } from './types';

export function RuleRelationsEditor({ relations = [], change, busy }: {
  relations?: RuleRelation[]; change: (relations: RuleRelation[]) => void; busy: boolean;
}) {
  const formId = useId();
  const update = (index: number, value: Partial<RuleRelation>) => {
    change(relations.map((relation, position) => position === index
      ? { ...relation, ...value } : relation));
  };
  return <fieldset>
    <legend>规则关系</legend>
    <p className="muted">关系候选用于讨论。选择“随当前提案确认”也只修改待审批内容，仍需明确批准整份提案。记录关系本身不会修改目标规则。</p>
    {relations.map((relation, index) => <fieldset key={index}>
      <legend>第 {index + 1} 条规则关系</legend>
      <label htmlFor={formId + '-type-' + index}>关系类型</label>
      <select id={formId + '-type-' + index} disabled={busy} value={relation.type}
        onChange={event => update(index, { type: event.target.value })}>
        <option value="conflicts_with">存在冲突</option>
        <option value="duplicate_of">重复关系</option>
        <option value="extends">扩展关系</option>
        <option value="narrows">限定关系</option>
        <option value="exception_to">例外关系</option>
        <option value="example_of">案例关系</option>
        <option value="supersedes">替代关系（目标规则仍需单独审阅）</option>
      </select>
      <label htmlFor={formId + '-target-' + index}>关系目标规则编号</label>
      <input id={formId + '-target-' + index} required disabled={busy}
        pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,100}" value={relation.target_id ?? ''}
        onChange={event => update(index, { target_id: event.target.value })} />
      <label htmlFor={formId + '-status-' + index}>关系状态</label>
      <select id={formId + '-status-' + index} disabled={busy}
        value={relation.status ?? 'candidate'}
        onChange={event => update(index, { status: event.target.value })}>
        <option value="candidate">候选关系（待讨论）</option>
        <option value="approved">随当前提案确认</option>
      </select>
      <button type="button" disabled={busy}
        onClick={() => change(relations.filter((_, position) => position !== index))}>
        移除第 {index + 1} 条关系
      </button>
    </fieldset>)}
    <button type="button" disabled={busy} onClick={() => change([...relations, {
      type: 'conflicts_with', target_id: '', status: 'candidate',
    }])}>添加规则关系</button>
  </fieldset>;
}
