import type { Feedback, Proposal, Rule } from './types';
import { TargetBindings } from './TargetBindings';

export function BatchRules({ proposal, approvedRules = [], feedback = [] }: {
  proposal: Proposal & { additional_rules?: Rule[]; additional_before?: Rule[] };
  approvedRules?: Rule[]; feedback?: Feedback[];
}) {
  const records = [proposal.after, ...(proposal.additional_rules ?? [])];
  const targets = new Map<string, Rule>(
    approvedRules.map(rule => [rule.id, rule] as const),
  );
  for (const record of records) targets.set(record.id, record);
  const originals = new Map([proposal.before, ...(proposal.additional_before ?? [])]
    .filter((rule): rule is Rule => Boolean(rule)).map(rule => [rule.id, rule]));
  return <section aria-label="完整提案内容">
    <h3>本次提案包含 {records.length} 条规则</h3>
    <p>批准将同时应用以下全部规则。请逐条核对当前内容、修改后内容和适用范围。</p>
    {records.map(rule => <article className="evidence" key={rule.id}>
      <h4>{rule.id} · {rule.short_title}</h4>
      <p>{rule.statement}</p>
      <TargetBindings rule={rule} targets={[...targets.values()]} feedback={feedback}
        plannedIds={records.map(record => record.id)} />
      <p>修改后状态：{rule.status === 'deprecated' ? '停用' : rule.status === 'active' ? '生效' : rule.status === 'proposed' ? '批准后生效' : rule.status}</p>
      <details open>
        <summary>{rule.id} 的完整修改前后内容</summary>
        <pre className="diff">{JSON.stringify({
          before: originals.get(rule.id) ?? null,
          after: rule,
        }, null, 2)}</pre>
      </details>
    </article>)}
  </section>;
}
