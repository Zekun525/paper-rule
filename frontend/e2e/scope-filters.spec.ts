import { test, expect } from '@playwright/test';

test.use({ viewport: { width: 1440, height: 1000 } });

test('desktop scope clarification requires approval and persists exact conditions', async ({ page, request }, testInfo) => {
  const suffix = Date.now();
  const paperId = 'SYNTHETIC-SCOPE-' + suffix;
  const otherPaperId = 'SYNTHETIC-OTHER-' + suffix;
  const ruleId = 'R-SCOPE-' + suffix;
  const title = 'Synthetic desktop scope ' + suffix;
  const baselineRules = await (await request.get('/api/rules')).json();
  for (const id of [paperId, otherPaperId]) {
    const saved = await request.post('/api/papers', { data: {
      paper_id: id, title: id, research_type: 'synthetic-theory',
      venue: 'SYNTHETIC-A', article_type: 'full',
    } });
    expect(saved.ok()).toBeTruthy();
  }
  const created = await request.post('/api/proposals', { data: { rule: {
    id: ruleId, short_title: title, statement: 'Explain each synthetic inference.',
    scope: { levels: ['paper'], paper_ids: [paperId],
      include: ['unknown:Proof'], exclude: ['venue:SYNTHETIC-B'],
      effective_from: '2020-01-01T00:00:00Z' },
  } } });
  expect(created.ok()).toBeTruthy();
  const proposal = await created.json();
  const approved = await request.post('/api/proposals/' + proposal.proposal_id + '/approve', {
    data: { proposal_hash: proposal.proposal_hash },
  });
  expect(approved.ok()).toBeTruthy();
  const activeBefore = await (await request.get('/api/rules')).json();

  async function preview(section = 'Proof', task = 'proof_rewrite') {
    await page.getByLabel('选择已保存论文', { exact: true }).selectOption(paperId);
    await page.locator('#context-section').fill(section);
    await page.locator('#context-task').fill(task);
    const response = page.waitForResponse(item =>
      item.url().endsWith('/api/context') && item.request().method() === 'POST');
    await page.getByRole('button', { name: '加载适用规则', exact: true }).click();
    const result = await response;
    expect(result.ok()).toBeTruthy();
    return result.json();
  }
  await page.goto('/');
  await page.getByRole('button', { name: '论文工作区', exact: true }).click();
  const unresolved = await preview();
  expect(unresolved.complete).toBe(false);
  expect(unresolved.scope_issues.some((item: { rule_id: string }) => item.rule_id === ruleId)).toBe(true);
  await expect(page.getByRole('heading', { name: '适用条件需要澄清', exact: true })).toBeVisible();

  await page.getByRole('button', { name: '规则知识库', exact: true }).click();
  await page.getByRole('button', { name: new RegExp(title) }).click();
  await page.getByRole('button', { name: '修改规则提案', exact: true }).click();
  await expect(page.getByLabel('额外适用条件 1 · 条件值', { exact: true })).toHaveValue('unknown:Proof');
  await page.getByRole('combobox', { name: '额外适用条件 1 · 条件类型', exact: true }).selectOption('section');
  await expect(page.getByLabel('额外适用条件 1 · 条件值', { exact: true })).toHaveValue('Proof');
  for (const [index, field, value] of [
    [2, 'paper', paperId], [3, 'venue', 'SYNTHETIC-A'], [4, 'task', 'temporary'],
  ] as const) {
    await page.getByRole('button', { name: '添加额外适用条件', exact: true }).click();
    await page.getByRole('combobox', { name: '额外适用条件 ' + index + ' · 条件类型', exact: true }).selectOption(field);
    await page.getByLabel('额外适用条件 ' + index + ' · 条件值', { exact: true }).fill(value);
  }
  await page.getByRole('button', { name: '移除额外适用条件 4', exact: true }).click();
  await page.getByRole('button', { name: '添加排除条件', exact: true }).click();
  await page.getByRole('combobox', { name: '排除条件 2 · 条件类型', exact: true }).selectOption('task');
  await page.getByLabel('排除条件 2 · 条件值', { exact: true }).fill('review');
  const research = page.getByLabel('研究类型（逗号分隔）', { exact: true });
  await research.fill('');
  await research.pressSequentially('synthetic-theory, synthetic-experiment');
  await page.getByLabel('任务类型（逗号分隔）', { exact: true }).fill('proof_rewrite, review');
  await page.getByLabel('例外说明（每行一条）', { exact: true })
    .fill(['Synthetic exception one.', 'Synthetic exception two.'].join(String.fromCharCode(10)));
  await page.getByRole('button', { name: '保存待审批版本', exact: true }).click();
  await expect(page.getByRole('heading', { name: '审批中心', exact: true })).toBeVisible();
  expect(await (await request.get('/api/rules')).json()).toEqual(activeBefore);
  await page.getByRole('button', { name: '批准当前第 1 版', exact: true }).click();
  await expect.poll(async () => (await (await request.get('/api/rules')).json())
    .find((item: { id: string }) => item.id === ruleId)?.version).toBe(2);
  const finalRules = await (await request.get('/api/rules')).json();
  const updated = finalRules.find((item: { id: string }) => item.id === ruleId);
  expect(updated.scope.include).toEqual(['section:Proof', 'paper:' + paperId, 'venue:SYNTHETIC-A']);
  expect(updated.scope.exclude).toEqual(['venue:SYNTHETIC-B', 'task:review']);
  expect(updated.scope.research_types).toEqual(['synthetic-theory', 'synthetic-experiment']);
  expect(updated.scope.task_types).toEqual(['proof_rewrite', 'review']);
  expect(updated.scope.exceptions).toEqual(['Synthetic exception one.', 'Synthetic exception two.']);
  expect(new Date(updated.scope.effective_from).toISOString()).toBe('2020-01-01T00:00:00.000Z');
  expect(finalRules.filter((item: { id: string }) => item.id !== ruleId)).toEqual(baselineRules);

  await page.reload();
  await page.getByRole('button', { name: '论文工作区', exact: true }).click();
  const matching = await preview();
  expect(matching.rules.some((item: { rule: { id: string } }) => item.rule.id === ruleId)).toBe(true);
  await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('windows-desktop-scope.png'), fullPage: true });
  for (const [section, task] of [['Proof', 'review'], ['Introduction', 'proof_rewrite']]) {
    const excluded = await preview(section, task);
    expect(excluded.rules.some((item: { rule: { id: string } }) => item.rule.id === ruleId)).toBe(false);
    await expect(page.getByRole('heading', { name: title, exact: true })).toHaveCount(0);
  }
  const other = await request.post('/api/context', { data: {
    paper_id: otherPaperId, section: 'Proof', task: 'proof_rewrite',
  } });
  expect(other.ok()).toBeTruthy();
  expect((await other.json()).rules.some((item: { rule: { id: string } }) => item.rule.id === ruleId)).toBe(false);
});
