import { test, expect } from '@playwright/test';

test('one-off feedback becomes an approved paper task without activating a rule',
  async ({ page, request }) => {
    const paperId = 'synthetic-one-off-' + Date.now();
    const title = 'Synthetic one-off browser task';
    const paper = await request.post('/api/papers', { data: {
      paper_id: paperId, title: 'Synthetic one-off browser paper',
    } });
    expect(paper.ok()).toBeTruthy();
    const baseline = await (await request.get('/api/rules')).json();
    await page.goto('/');
    await page.getByRole('button', { name: '来源与意见', exact: true }).click();
    await page.getByRole('combobox', { name: '关联论文', exact: true }).selectOption(paperId);
    await page.getByLabel('上传材料').setInputFiles({
      name: 'synthetic-one-off-review.txt', mimeType: 'text/plain',
      buffer: Buffer.from('Swap these two synthetic paragraphs in this paper only.'),
    });
    await page.getByRole('button', { name: /synthetic-one-off-review.txt/ }).click();
    await expect(page.getByText('Swap these two synthetic paragraphs in this paper only.',
      { exact: true })).toBeVisible();
    await page.getByText('补充解释或纠错', { exact: true }).click();
    await page.getByLabel('修正或补充的解释', { exact: true })
      .fill('Swap the two synthetic introduction paragraphs in this paper only.');
    await page.getByLabel('修正依据', { exact: true })
      .fill('Synthetic reviewer confirmed a one-off edit.');
    await page.getByLabel('补充确认分类', { exact: true }).selectOption('one_off_edit');
    await page.getByRole('button', { name: '追加纠错记录', exact: true }).click();
    await expect(page.getByText('当前确认分类：当前论文的一次性修改',
      { exact: true })).toBeVisible();
    await page.getByText('整理为论文修改任务', { exact: true }).click();
    await page.getByLabel('任务所属论文', { exact: true }).selectOption(paperId);
    await page.getByLabel('任务标题', { exact: true }).fill(title);
    await page.getByLabel('任务修改内容', { exact: true })
      .fill('Swap the first two synthetic introduction paragraphs in this paper only.');
    await page.getByRole('button', { name: '保存任务提案', exact: true }).click();
    await expect(page.getByRole('heading', { name: '审批中心', exact: true })).toBeVisible();
    expect(await (await request.get('/api/tasks')).json()).toEqual([]);
    expect(await (await request.get('/api/rules')).json()).toEqual(baseline);
    await page.getByRole('button', { name: '批准当前第 1 版', exact: true }).click();
    await expect(page.getByRole('button', { name: '批准当前第 1 版', exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: '论文修改任务', exact: true }).click();
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
    await page.reload();
    await page.getByRole('button', { name: '论文修改任务', exact: true }).click();
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
    const tasks = await (await request.get('/api/tasks')).json();
    const task = tasks.find((item: { record: { short_title: string } }) =>
      item.record.short_title === title);
    expect(task.paper_id).toBe(paperId);
    expect(task.proposal_hash).toMatch(/^[a-f0-9]{64}$/);
    expect(task.record.scope.levels).toEqual(['paper']);
    expect(task.record.scope.paper_ids).toEqual([paperId]);
    expect(await (await request.get('/api/rules')).json()).toEqual(baseline);
    await page.getByRole('button', { name: '查看审批提案', exact: true }).click();
    await expect(page.getByRole('heading', { name: '审批中心', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
  });
