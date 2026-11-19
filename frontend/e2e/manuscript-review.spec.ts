import { randomUUID } from 'node:crypto';
import { test, expect, type APIRequestContext, type Page } from '@playwright/test';

test.use({ viewport: { width: 1440, height: 1000 } });

async function seedSyntheticPaper(request: APIRequestContext) {
  const suffix = Date.now() + '-' + randomUUID().slice(0, 8);
  const paperId = 'SYNTHETIC-MANUSCRIPT-' + suffix;
  const phrase = 'synthetic-unsupported-' + suffix;
  const phraseRuleId = 'R-PHRASE-' + suffix;
  const semanticRuleId = 'R-SEMANTIC-' + suffix;
  const paper = await request.post('/api/papers', {
    data: { paper_id: paperId, title: 'Synthetic manuscript ' + suffix },
  });
  expect(paper.ok()).toBeTruthy();
  for (const [id, statement, method] of [
    [phraseRuleId, 'avoid: ' + phrase, 'deterministic'],
    [semanticRuleId, 'Explain synthetic assumptions before drawing the inference.', 'semantic'],
  ]) {
    const created = await request.post('/api/proposals', { data: {
      rule: {
        id, short_title: 'Synthetic manuscript rule ' + id,
        statement, check_method: method,
        scope: { levels: ['paper'], paper_ids: [paperId] },
      },
    } });
    expect(created.ok()).toBeTruthy();
    const proposal = await created.json();
    const approved = await request.post('/api/proposals/' + proposal.proposal_id + '/approve', {
      data: { proposal_hash: proposal.proposal_hash },
    });
    expect(approved.ok()).toBeTruthy();
  }
  return {
    paperId, phrase, phraseRuleId, semanticRuleId,
    rules: await (await request.get('/api/rules')).json(),
    proposals: await (await request.get('/api/proposals')).json(),
  };
}

async function openPaper(page: Page, paperId: string) {
  await page.goto('/');
  await page.getByRole('button', { name: '论文工作区', exact: true }).click();
  await page.getByRole('combobox', { name: '选择已保存论文', exact: true }).selectOption(paperId);
  await expect(page.getByRole('heading', { name: '发起论文审查', exact: true })).toBeVisible();
}

test('Windows pasted manuscript review persists actual findings without changing approved rules', async ({ page, request }, testInfo) => {
  const seeded = await seedSyntheticPaper(request);
  const text = 'Synthetic context.' + String.fromCharCode(10)
    + 'This ' + seeded.phrase + ' claim lacks supporting evidence.';
  await openPaper(page, seeded.paperId);
  const form = page.getByRole('region', { name: '发起论文审查', exact: true });
  await expect(form.getByRole('checkbox')).not.toBeChecked();
  await form.getByLabel('稿件文件名', { exact: true }).fill('synthetic-pasted.tex');
  await form.getByLabel('稿件原文', { exact: true }).fill(text);
  await form.getByLabel('本次审查章节', { exact: true }).fill('Proof');
  await form.getByLabel('本次审查任务', { exact: true }).fill('proof_rewrite');
  const responsePromise = page.waitForResponse(response =>
    response.url().endsWith('/api/reviews/check') && response.request().method() === 'POST');
  await form.getByRole('button', { name: '开始审查并保存报告', exact: true }).click();
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  const sent = response.request().postDataJSON();
  expect(sent.semantic).toBe(false);
  expect(sent.send_to_provider).toBe(false);
  expect(sent.text).toBe(text);
  const report = await response.json();
  expect(report.paper_id).toBe(seeded.paperId);
  expect(report.section).toBe('Proof');
  expect(report.task).toBe('proof_rewrite');
  expect(report.status).toBe('incomplete');
  expect(report.semantic_status).toBe('not_reviewed');
  expect(report.semantic_evidence).toEqual([]);
  const findings = report.findings.filter((item: { rule_id: string }) =>
    item.rule_id === seeded.phraseRuleId);
  expect(findings).toHaveLength(1);
  expect(findings[0].location).toBe('synthetic-pasted.tex:2');
  expect(findings[0].quote).toBe(text.split(String.fromCharCode(10))[1]);
  expect(findings[0].confirmed).toBeNull();
  await expect(page.getByText('报告编号：' + report.review_id, { exact: true })).toBeVisible();
  await expect(page.getByText(
    '审查报告已保存，请核对逐条检查结果和待人工确认的问题。生效规则没有改变。',
    { exact: true },
  )).toBeVisible();
  const exported = await request.get('/api/reviews/' + report.review_id + '/report');
  expect(exported.ok()).toBeTruthy();
  expect(await exported.json()).toEqual(report);
  await page.screenshot({
    path: testInfo.outputPath('windows-pasted-manuscript-review.png'), fullPage: true,
  });
  await page.reload();
  await page.getByRole('button', { name: '论文工作区', exact: true }).click();
  await page.getByRole('combobox', { name: '选择已保存论文', exact: true }).selectOption(seeded.paperId);
  await expect(page.getByText('报告编号：' + report.review_id, { exact: true })).toBeVisible();
  expect(await (await request.get('/api/rules')).json()).toEqual(seeded.rules);
  expect(await (await request.get('/api/proposals')).json()).toEqual(seeded.proposals);
});

test('Windows manuscript file review requires explicit AI selection and preserves unavailable status', async ({ page, request }, testInfo) => {
  const seeded = await seedSyntheticPaper(request);
  const text = 'A ' + seeded.phrase + ' synthetic claim needs an explanation.';
  await openPaper(page, seeded.paperId);
  const form = page.getByRole('region', { name: '发起论文审查', exact: true });
  await form.getByLabel('选择 UTF-8 文本文件（可选）', { exact: true }).setInputFiles({
    name: 'synthetic-upload.tex', mimeType: 'text/plain', buffer: Buffer.from(text, 'utf8'),
  });
  await expect(form.getByLabel('稿件原文', { exact: true })).toHaveValue(text);
  await expect(form.getByLabel('稿件文件名', { exact: true })).toHaveValue('synthetic-upload.tex');
  await expect(form.getByRole('checkbox')).not.toBeChecked();
  await expect(form.getByLabel('最多 AI 请求次数', { exact: true })).toHaveCount(0);
  const before = await (await request.get('/api/reviews')).json();
  expect(before.filter((item: { paper_id: string }) => item.paper_id === seeded.paperId)).toEqual([]);
  await form.getByRole('checkbox').check();
  await form.getByLabel('最多 AI 请求次数', { exact: true }).fill('1');
  const responsePromise = page.waitForResponse(response =>
    response.url().endsWith('/api/reviews/check') && response.request().method() === 'POST');
  await form.getByRole('button', { name: '开始审查并保存报告', exact: true }).click();
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  const sent = response.request().postDataJSON();
  expect(sent.semantic).toBe(true);
  expect(sent.send_to_provider).toBe(true);
  expect(sent.max_semantic_calls).toBe(1);
  const report = await response.json();
  expect(report.status).toBe('incomplete');
  expect(report.semantic_status).toBe('not_reviewed');
  const semantic = report.semantic_evidence.find((item: { rule_id: string }) =>
    item.rule_id === seeded.semanticRuleId);
  expect(semantic.error).toBe('semantic_provider_unavailable');
  expect(semantic.checked_line_count).toBe(0);
  expect(semantic.human_review).toBe('pending');
  expect(semantic.formal_proof_status).toBe('not_performed');
  expect(report.findings.some((item: { rule_id: string }) =>
    item.rule_id === seeded.phraseRuleId)).toBe(true);
  await expect(page.getByText('报告编号：' + report.review_id, { exact: true })).toBeVisible();
  await page.getByText(/^查看 AI 审查依据/).click();
  await expect(page.getByText(
    '尚未配置可用的 AI 服务，请在设置中检查配置', { exact: true },
  ).first()).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath('windows-manuscript-ai-unavailable.png'), fullPage: true,
  });
  const stored = await (await request.get('/api/reviews')).json();
  expect(stored.find((item: { review_id: string }) => item.review_id === report.review_id)).toEqual(report);
  expect(await (await request.get('/api/rules')).json()).toEqual(seeded.rules);
  expect(await (await request.get('/api/proposals')).json()).toEqual(seeded.proposals);
});
