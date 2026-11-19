import { test, expect } from '@playwright/test';

test.use({ viewport: { width: 1440, height: 1000 } });

test('synthetic successful analysis UI opens an editable draft and requires actual approval', async ({ page, request }, testInfo) => {
  const suffix = Date.now();
  const filename = 'synthetic-analysis-ui-' + suffix + '.txt';
  const baseline = await (await request.get('/api/rules')).json();
  const imported = await request.post('/api/sources', { data: {
    filename, content_base64: Buffer.from('Explain the synthetic inference.').toString('base64'),
  } });
  expect(imported.ok()).toBeTruthy();
  const evidence = (await imported.json()).feedback[0];
  const ruleId = 'R-SYNTHETIC-AI-UI-' + suffix;
  const fixture = {
    analysis_id: 'AN-SYNTHETIC-UI', created_at: '2026-11-18T00:00:00Z',
    status: 'suggested', stale: false, provider: 'synthetic-ui-fixture', model: 'synthetic-model',
    error: null, classification_confirmed: false, proposal_created: false,
    candidate_rules: [],
    suggestion: {
      classification: 'reusable_rule', explanation: 'Synthetic fixture requests clearer reasoning.',
      related_rules: [],
      rule: { id: ruleId, version: 1, status: 'proposed', short_title: 'Synthetic AI draft ' + suffix,
        statement: 'Explain the synthetic inference.', scope: { levels: ['global'] },
        check_method: 'semantic', source_feedback_ids: [evidence.id] },
    },
  };
  // Only the analysis result is a browser fixture. Proposal creation and approval
  // use the real backend; this test does not establish real-model quality.
  await page.route('**/api/feedback/' + evidence.id + '/analyses', async route => {
    await route.fulfill({ json: route.request().method() === 'GET' ? [fixture] : fixture });
  });
  await page.goto('/');
  await page.getByRole('button', { name: '来源与意见', exact: true }).click();
  await page.getByRole('button', { name: new RegExp(filename) }).click();
  await page.getByRole('button', { name: '请求 AI 整理', exact: true }).click();
  await expect(page.getByText('AI 建议分类：可复用写作规范（尚未确认）', { exact: true })).toBeVisible();
  await expect(page.getByText('Synthetic fixture requests clearer reasoning.', { exact: true })).toBeVisible();
  expect(await (await request.get('/api/rules')).json()).toEqual(baseline);
  expect((await (await request.get('/api/feedback')).json())
    .find((row: { id: string }) => row.id === evidence.id)).toEqual(evidence);
  await page.getByRole('button', { name: '编辑 AI 建议草稿', exact: true }).click();
  await expect(page.getByLabel('规则内容', { exact: true })).toHaveValue('Explain the synthetic inference.');
  await page.getByLabel('规则内容', { exact: true }).fill('Explain the synthetic assumptions before the inference.');
  await page.getByRole('button', { name: '保存待审批版本', exact: true }).click();
  await expect(page.getByRole('heading', { name: '审批中心', exact: true })).toBeVisible();
  expect(await (await request.get('/api/rules')).json()).toEqual(baseline);
  await page.screenshot({ path: testInfo.outputPath('windows-synthetic-ai-draft-approval.png'), fullPage: true });
  await page.getByRole('button', { name: '批准当前第 1 版', exact: true }).click();
  await expect.poll(async () => (await (await request.get('/api/rules')).json())
    .find((row: { id: string }) => row.id === ruleId)?.statement)
    .toBe('Explain the synthetic assumptions before the inference.');
  const rules = await (await request.get('/api/rules')).json();
  expect(rules.filter((row: { id: string }) => row.id !== ruleId)).toEqual(baseline);
  expect((await (await request.get('/api/feedback')).json())
    .find((row: { id: string }) => row.id === evidence.id)).toEqual(evidence);
});
