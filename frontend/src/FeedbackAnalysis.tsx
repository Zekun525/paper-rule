import { useState } from 'react';
import { request } from './api';
import type { Feedback, Rule } from './types';
import { classifications, currentClassification } from './FeedbackEvidence';

type Analysis = {
  analysis_id: string; created_at: string; status: string; stale: boolean;
  provider: string; model: string | null; error: string | null;
  candidate_rules: Rule[];
  suggestion: null | {
    classification: string; explanation: string; rule: Rule | null;
    example?: null | {
      title: string; focus: string; section: string; page: number | null;
      quote: string; writing_feature: string; adapted_example: string; limitations: string;
      source_id: string; source_sha256: string; feedback_id: string; feedback_sha256: string;
      source_location: { page_index?: number | null };
      human_review: string; mandatory_rule: boolean;
    };
    related_rules: {
      rule_id: string; rule_version: number; relation: string; reason: string;
    }[];
  };
};

const relationLabels: { [key: string]: string } = {
  extends: '完善旧规则', narrows: '限定适用范围', exception_to: '补充例外',
  conflicts_with: '存在分歧', duplicate_of: '可能重复',
};

export function FeedbackAnalysis({ item, busy, run, draft }: {
  item: Feedback; busy: boolean;
  run: (task: () => Promise<void>) => void;
  draft: (rule: Rule) => void;
}) {
  const [records, setRecords] = useState([] as Analysis[]);
  const [message, setMessage] = useState('');
  const endpoint = '/feedback/' + encodeURIComponent(item.id) + '/analyses';
  async function readRecords(): Promise<void> {
    setRecords(await request(endpoint) as Analysis[]);
  }
  async function editDraft(record: Analysis) {
    const current = (await request(endpoint) as Analysis[])
      .find(entry => entry.analysis_id === record.analysis_id);
    if (!current || current.stale || !current.suggestion?.rule) {
      await readRecords();
      setMessage('意见、来源、论文档案或规则已改变，请重新请求 AI 整理后再编辑草稿。');
      return;
    }
    if (currentClassification(item) === 'one_off_edit') {
      setMessage('当前已确认分类为一次性修改，请先核对并明确重新分类。');
      return;
    }
    const rule = current.suggestion.rule;
    draft({
      ...rule,
      relations: current.suggestion.related_rules.map(link => ({
        type: link.relation, target_id: link.rule_id, status: 'candidate',
      })),
    });
    setMessage('已打开可编辑草稿。保存后仍需在审批中心明确批准。');
  }
  return <section aria-label="AI 整理建议">
    <h4>AI 整理意见</h4>
    <p className="muted">
      请求时会把本条意见、来源说明、论文档案和最多五条适用旧规则发送给已配置的 AI 服务。
      分类和关联均为建议；原话、当前确认分类和生效规则保持原样。
    </p>
    <div className="actions">
      <button disabled={busy} onClick={() => run(async () => {
        setMessage('');
        await request(endpoint, { expected_sha256: item.sha256 });
        await readRecords();
      })}>请求 AI 整理</button>
      <button disabled={busy} onClick={() => run(readRecords)}>查看 AI 整理历史</button>
    </div>
    {message && <p role="status">{message}</p>}
    {[...records].reverse().map(record => <article className="evidence" key={record.analysis_id}>
      <small>{record.created_at} · {record.provider}{record.model ? ' · ' + record.model : ''}</small>
      {record.stale && <p role="alert">意见、来源、论文档案或规则已改变，此建议仅供历史查看，请重新整理。</p>}
      {record.status !== 'suggested' && <p role="status">
        AI 未能完成有效整理。意见已保留，可以重试或人工编辑。
        {record.error ? '（' + record.error + '）' : ''}
      </p>}
      {record.suggestion && <>
        <p>AI 建议分类：{classifications[record.suggestion.classification]
          ?? record.suggestion.classification}（尚未确认）</p>
        <p>{record.suggestion.explanation}</p>
        {record.suggestion.example && <section aria-label="范文写作案例">
          <h5>{record.suggestion.example.title}</h5>
          <p className="muted">候选写作案例，尚需人工核对；不是强制规则，也不应直接复制范文。</p>
          <p>学习目标：{record.suggestion.example.focus}</p>
          <p>原文位置：{record.suggestion.example.section}
            {record.suggestion.example.page != null
              ? ' · 第 ' + record.suggestion.example.page + ' 页' : ' · 原件未记录页码'}</p>
          <blockquote>{record.suggestion.example.quote}</blockquote>
          <p>可借鉴特征：{record.suggestion.example.writing_feature}</p>
          <h6>改写示例（仅作写法演示）</h6>
          <p>{record.suggestion.example.adapted_example}</p>
          <p>适用限制：{record.suggestion.example.limitations}</p>
          <details>
            <summary>查看案例来源依据</summary>
            <p>来源：{record.suggestion.example.source_id}</p>
            <p>原件 SHA-256：{record.suggestion.example.source_sha256}</p>
            <p>意见记录：{record.suggestion.example.feedback_id}</p>
            {record.suggestion.example.source_location.page_index != null && <img
              className="pdf-preview" alt="范文案例所在原始 PDF 页面" loading="lazy"
              src={'/api/sources/' + encodeURIComponent(record.suggestion.example.source_id)
                + '/preview/' + record.suggestion.example.source_location.page_index} />}
          </details>
        </section>}
        <p className="muted">核对分类后，可通过本条意见的“补充解释或纠错”明确确认。AI 建议不会代替确认。</p>
        {record.suggestion.related_rules.map(link => {
          const old = record.candidate_rules.find(rule =>
            rule.id === link.rule_id && rule.version === link.rule_version);
          return <div key={link.rule_id + ':' + link.relation}>
            <p>{relationLabels[link.relation] ?? link.relation}：{link.reason}</p>
            {old && <details>
              <summary>{old.short_title} · {old.id} · v{old.version}</summary>
              <p>{old.statement}</p>
              <p>来源意见：{old.source_feedback_ids?.join('、') || '未关联来源意见'}</p>
              <pre>{JSON.stringify(old.scope, null, 2)}</pre>
            </details>}
          </div>;
        })}
        {record.suggestion.rule && <>
          <h5>{record.suggestion.rule.short_title}</h5>
          <p>{record.suggestion.rule.statement}</p>
          <p>{record.suggestion.rule.rationale}</p>
          <button disabled={busy || record.stale || currentClassification(item) === 'one_off_edit'}
            onClick={() => run(() => editDraft(record))}>编辑 AI 建议草稿</button>
        </>}
      </>}
    </article>)}
  </section>;
}
