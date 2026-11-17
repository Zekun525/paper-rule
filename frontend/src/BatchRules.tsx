import type { Proposal, Rule } from './types';

export function BatchRules({ proposal }: {
  proposal: Proposal & { additional_rules?: Rule[]; additional_before?: Rule[] };
}) {
  const records = [proposal.after, ...(proposal.additional_rules ?? [])];
  const originals = new Map([proposal.before, ...(proposal.additional_before ?? [])]
    .filter((rule): rule is Rule => Boolean(rule)).map(rule => [rule.id, rule]));
  return <section aria-label="完整提案内容">
    <h3>本次提案包含 {records.length} 条规则</h3>
    <p>批准将同时应用以下全部规则。请逐条核对当前内容、修改后内容和适用范围。</p>
    {records.map(rule => <article className="evidence" key={rule.id}>
      <h4>{rule.id} · {rule.short_title}</h4>
      <p>{rule.statement}</p>
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
