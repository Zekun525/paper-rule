import type { Feedback, Rule } from './types';

const relationLabels: Record<string, string> = {
  narrows: '限定关系', exception_to: '例外关系', supersedes: '替代关系',
};

function RelatedTarget({ target, planned, feedback }: {
  target?: Rule; planned: boolean; feedback: Feedback[];
}) {
  if (!target) return <p className="warning">当前无法读取目标规则内容，请核对目标编号。</p>;
  const evidence = feedback.filter(item => (target.source_feedback_ids ?? []).includes(item.id));
  return <section aria-label={'关联规则内容 ' + target.id}>
    <h5>{planned ? '同批待审批目标内容' : '当前可读取的目标内容'}</h5>
    <p>{target.id} · {target.short_title}{!planned && ' · v' + target.version}</p>
    <p>{target.statement}</p>
    <details>
      <summary>查看目标的完整适用条件</summary>
      <pre className="diff">{JSON.stringify(target.scope, null, 2)}</pre>
    </details>
    {evidence.map(item => <blockquote key={item.id}>
      {item.quote}<small>{item.reviewer_id} · {item.id}</small>
    </blockquote>)}
    {!evidence.length && <p className="muted">当前没有可展示的关联原始意见。</p>}
    <p className="muted">这里展示当前可读取的内容；批准时仍会核对提案绑定的目标版本和内容。</p>
  </section>;
}

export function TargetBindings({ rule, targets = [], feedback = [], plannedIds = [] }: {
  rule: Rule; targets?: Rule[]; feedback?: Feedback[]; plannedIds?: string[];
}) {
  const relations = (rule.relations ?? []).filter(relation =>
    relation.status === 'approved' && Object.hasOwn(relationLabels, relation.type));
  if (!relations.length) return null;
  return <section aria-label={'规则关系目标 ' + rule.id}>
    <h5>本提案记录的规则关系目标</h5>
    <p>目标版本属于这份提案的固定内容。是否已生效，以提案状态为准；目标变化后需要重新核对。</p>
    {relations.map((relation, index) => <article
      key={relation.type + ':' + relation.target_id + ':' + index}>
      <p>{relationLabels[relation.type]}</p>
      {relation.target_version && relation.target_sha256 ? <>
        <p>{'本版提案绑定的目标：' + relation.target_id + ' · v' +
          relation.target_version}</p>
        <details>
          <summary>查看目标内容校验值</summary>
          <code>{relation.target_sha256}</code>
        </details>
      </> : <p className="warning">
        这条关系缺少目标版本记录，批准前需要重新建立并核对提案。
      </p>}
      <RelatedTarget target={targets.find(target => target.id === relation.target_id)}
        planned={plannedIds.includes(relation.target_id)} feedback={feedback} />
    </article>)}
  </section>;
}
