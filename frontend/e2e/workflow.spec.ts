import { test, expect } from '@playwright/test';

test('import, revise, approve, persist, regress, and propose a historical revert', async ({ page, request }) => {
  const baselineRules = await (await request.get('/api/rules')).json();
  await page.goto('/');
  await page.getByRole('button', { name: '来源与意见', exact: true }).click();
  await page.getByLabel('上传材料').setInputFiles({
    name: 'synthetic-review.txt', mimeType: 'text/plain',
    buffer: Buffer.from('Avoid unsupported claims such as obviously in a proof.'),
  });
  await expect(page.getByRole('button', { name: /synthetic-review.txt/ })).toBeVisible();
  await expect(page.getByText('Avoid unsupported claims such as obviously in a proof.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '据此创建提案' }).click();
  const ruleId = await page.getByLabel('规则编号', { exact: true }).inputValue();
  expect(ruleId).toBeTruthy();
  await page.getByLabel('标题', { exact: true }).fill('Synthetic proof clarity');
  await page.getByLabel('规则内容', { exact: true }).fill('avoid: obviously');
  await page.getByLabel('检查方式').selectOption('deterministic');
  await page.getByRole('button', { name: '保存待审批版本' }).click();
  await expect(page.getByRole('heading', { name: '审批中心', exact: true })).toBeVisible();
  expect(await (await request.get('/api/rules')).json()).toEqual(baselineRules);
  await page.getByLabel('讨论内容').fill('Please keep this scoped as a writing rule.');
  await page.getByRole('button', { name: '发送讨论', exact: true }).click();
  await expect(page.getByText('Please keep this scoped as a writing rule.', { exact: true })).toBeVisible();
  expect(await (await request.get('/api/rules')).json()).toEqual(baselineRules);
  await page.getByRole('button', { name: '直接修改提案' }).click();
  await page.getByLabel('规则内容', { exact: true }).fill('avoid: clearly');
  await page.getByRole('button', { name: '保存待审批版本' }).click();
  await expect(page.getByRole('button', { name: '批准当前第 3 版' })).toBeVisible();
  expect(await (await request.get('/api/rules')).json()).toEqual(baselineRules);
  await page.getByRole('button', { name: '批准当前第 3 版' }).click();
  await expect(page.getByRole('button', { name: '批准当前第 3 版' })).toHaveCount(0);
  const rules = (await (await request.get('/api/rules')).json())
    .filter((item: { id: string }) => item.id === ruleId);
  expect(rules).toHaveLength(1);
  expect(rules[0].statement).toBe('avoid: clearly');
  await page.reload();
  await page.getByRole('button', { name: '规则知识库', exact: true }).click();
  await page.getByRole('button', { name: /Synthetic proof clarity/ }).click();
  await expect(page.getByRole('heading', { name: 'Synthetic proof clarity' })).toBeVisible();
  await page.getByRole('button', { name: '修改规则提案' }).click();
  await page.getByLabel('规则内容', { exact: true }).fill('avoid: obviously');
  await page.getByRole('button', { name: '保存待审批版本' }).click();
  await page.getByRole('button', { name: '批准当前第 1 版' }).click();
  await expect.poll(async () => (await (await request.get('/api/rules')).json())
    .find((item: { id: string }) => item.id === ruleId)?.version).toBe(2);
  await page.getByRole('button', { name: '规则知识库', exact: true }).click();
  await page.getByRole('button', { name: /Synthetic proof clarity/ }).click();
  await page.getByRole('button', { name: '以此版本创建回退提案' }).first().click();
  await expect(page.getByRole('heading', { name: '审批中心', exact: true })).toBeVisible();
  expect((await (await request.get('/api/rules')).json())
    .find((item: { id: string }) => item.id === ruleId)?.version).toBe(2);
  await page.getByRole('button', { name: '回归测试', exact: true }).click();
  await page.getByLabel('关联规则', { exact: true }).selectOption(rules[0].id);
  await page.getByLabel('待检查的例句').fill('This is obviously true.');
  await page.getByRole('button', { name: '保存回归案例' }).click();
  await expect(page.getByText('This is obviously true.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '运行已保存案例' }).click();
  await expect(page.getByText('1 个案例：1 通过，0 失败，0 未检查')).toBeVisible();
  const reportURL = await page.getByRole('link', { name: '导出 JSON' }).first().getAttribute('href');
  const exported = await request.get(reportURL!);
  expect(exported.ok()).toBeTruthy();
  expect((await exported.json()).passed).toBe(1);
  const finalRules = await (await request.get('/api/rules')).json();
  expect(finalRules.filter((item: { id: string }) => item.id !== ruleId)).toEqual(baselineRules);
});

test('paper workspace saves profiles and recalculates venue and article scope without losing facts', async ({ page, request }, testInfo) => {
  const paperId = 'synthetic-browser-paper-' + Date.now();
  const title = 'Synthetic browser paper workspace';
  const scopedTitle = 'Synthetic full article discussion';
  const ruleId = 'R-BROWSER-PAPER-' + Date.now();
  await page.goto('/');
  await page.getByRole('button', { name: '论文工作区', exact: true }).click();
  await page.getByLabel('论文编号', { exact: true }).fill(paperId);
  await page.getByLabel('论文标题', { exact: true }).fill(title);
  await page.getByLabel('研究类型', { exact: true }).fill('synthetic-theory');
  await page.getByLabel('投稿期刊', { exact: true }).fill('SYNTHETIC-A');
  await page.getByLabel('文章类型', { exact: true }).fill('full');
  await page.getByRole('button', { name: '保存论文档案', exact: true }).click();
  await expect(page.getByText('论文档案已保存。预览将使用保存后的投稿目标和文章类型。')).toBeVisible();

  const stored = (await (await request.get('/api/papers')).json())
    .find((item: { paper_id: string }) => item.paper_id === paperId);
  expect(stored.venue).toBe('SYNTHETIC-A');
  const facts = ['Synthetic theorem requires independent samples.'];
  const terms = ['synthetic-bound'];
  const seeded = await request.post('/api/papers', { data: { ...stored, facts, terms } });
  expect(seeded.ok()).toBeTruthy();
  const created = await request.post('/api/proposals', {
    data: {
      rule: {
        id: ruleId, short_title: scopedTitle,
        statement: 'Provide the full discussion for this synthetic article.',
        scope: {
          levels: ['publication'], paper_ids: [paperId],
          venues: ['SYNTHETIC-A'], article_types: ['full'],
        },
      },
    },
  });
  expect(created.ok()).toBeTruthy();
  const proposal = await created.json();
  const approved = await request.post('/api/proposals/' + proposal.proposal_id + '/approve', {
    data: { proposal_hash: proposal.proposal_hash },
  });
  expect(approved.ok()).toBeTruthy();

  await page.reload();
  await page.getByRole('button', { name: '论文工作区', exact: true }).click();
  await page.getByRole('button', { name: new RegExp(title) }).click();
  const matchingResponse = page.waitForResponse(response =>
    response.url().endsWith('/api/context') && response.request().method() === 'POST');
  await page.getByRole('button', { name: '加载适用规则', exact: true }).click();
  expect((await matchingResponse).ok()).toBeTruthy();
  await expect(page.getByRole('heading', { name: scopedTitle, exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('synthetic-paper-workspace.png'), fullPage: true });

  await page.getByLabel('文章类型', { exact: true }).fill('letter');
  await page.getByRole('button', { name: '保存论文档案', exact: true }).click();
  await expect(page.getByText('论文档案已保存。预览将使用保存后的投稿目标和文章类型。')).toBeVisible();
  const letterResponse = page.waitForResponse(response =>
    response.url().endsWith('/api/context') && response.request().method() === 'POST');
  await page.getByRole('button', { name: '加载适用规则', exact: true }).click();
  const letterBundle = await (await letterResponse).json();
  expect(letterBundle.rules.some((item: { rule: { id: string } }) => item.rule.id === ruleId)).toBe(false);
  await expect(page.getByText('规则快照：', { exact: false })).toBeVisible();
  await expect(page.getByRole('heading', { name: scopedTitle, exact: true })).toHaveCount(0);

  await page.getByLabel('文章类型', { exact: true }).fill('full');
  await page.getByLabel('投稿期刊', { exact: true }).fill('SYNTHETIC-B');
  await page.getByRole('button', { name: '保存论文档案', exact: true }).click();
  await expect(page.getByText('论文档案已保存。预览将使用保存后的投稿目标和文章类型。')).toBeVisible();
  const changedResponse = page.waitForResponse(response =>
    response.url().endsWith('/api/context') && response.request().method() === 'POST');
  await page.getByRole('button', { name: '加载适用规则', exact: true }).click();
  const changedBundle = await (await changedResponse).json();
  expect(changedBundle.rules.some((item: { rule: { id: string } }) => item.rule.id === ruleId)).toBe(false);
  await expect(page.getByText('规则快照：', { exact: false })).toBeVisible();
  await expect(page.getByRole('heading', { name: scopedTitle, exact: true })).toHaveCount(0);
  const saved = (await (await request.get('/api/papers')).json())
    .find((item: { paper_id: string }) => item.paper_id === paperId);
  expect(saved.venue).toBe('SYNTHETIC-B');
  expect(saved.article_type).toBe('full');
  expect(saved.facts).toEqual(facts);
  expect(saved.terms).toEqual(terms);
});

test('settings accurately reports manual AI and local memory without changing active rules', async ({ page, request }, testInfo) => {
  const rulesBefore = await (await request.get('/api/rules')).json();
  await page.goto('/');
  await page.getByRole('button', { name: '设置与诊断', exact: true }).click();
  await expect(page.getByRole('heading', { name: '本地服务与 AI 配置', exact: true })).toBeVisible();
  await expect(page.getByText('当前模式：人工编辑', { exact: true })).toBeVisible();
  await expect(page.getByText('当前为人工编辑模式，未连接可用的 AI 服务。', { exact: true })).toBeVisible();
  await expect(page.getByText('状态：仅保存在本机', { exact: true })).toBeVisible();
  await expect(page.getByText('私有远端：尚未配置，仅在本机保存', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '推送已批准记录', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: '拉取私有记忆更新', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: '查看本机与远端差异', exact: true })).toBeDisabled();
  const diagnosticsResponse = page.waitForResponse(response =>
    response.url().endsWith('/api/diagnostics') && response.request().method() === 'GET');
  await page.getByRole('button', { name: '重新检查状态', exact: true }).click();
  const diagnostics = await (await diagnosticsResponse).json();
  expect(diagnostics.provider.configured).toBe(false);
  expect(diagnostics.provider.connection).toBe('not_checked');
  await expect(page.getByText('当前模式：人工编辑', { exact: true })).toBeVisible();
  expect(await (await request.get('/api/rules')).json()).toEqual(rulesBefore);
  await page.screenshot({ path: testInfo.outputPath('synthetic-settings.png'), fullPage: true });
});
