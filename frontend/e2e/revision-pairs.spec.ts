import { createHash } from 'node:crypto';
import { test, expect } from '@playwright/test';

test('Windows revision-pair import preserves originals and reloads verified differences', async ({
  page, request,
}) => {
  const rulesBefore = await (await request.get('/api/rules')).json();
  const proposalsBefore = await (await request.get('/api/proposals')).json();
  const commitBefore = (await (await request.get('/api/sync')).json()).commit;
  const before = Buffer.from('Assume $x \\le y$.' + String.fromCharCode(13, 10), 'utf8');
  const after = Buffer.from(
    'Assume $x \\le y$, under the stated condition.' + String.fromCharCode(13, 10), 'utf8',
  );
  await page.goto('/');
  await page.getByRole('button', { name: '来源与意见', exact: true }).click();
  await page.getByText('填写来源、论文和日期（可选）', { exact: true }).click();
  await page.getByLabel('来源代号', { exact: true }).fill('synthetic-pair-browser');
  await page.getByRole('combobox', { name: '来源角色', exact: true }).selectOption('collaborator');
  await page.getByLabel('材料日期', { exact: true }).fill('2026-11-19');
  await page.getByLabel('学习目标 / 来源说明', { exact: true })
    .fill('Compare the synthetic assumption clarification.');
  await page.getByText('导入修改前后对照', { exact: true }).click();
  const form = page.getByRole('region', { name: '修改前后对照导入', exact: true });
  await form.getByLabel('修改前文件', { exact: true }).setInputFiles({
    name: 'synthetic-browser-before.tex', mimeType: 'text/plain', buffer: before,
  });
  await form.getByLabel('修改后文件', { exact: true }).setInputFiles({
    name: 'synthetic-browser-after.tex', mimeType: 'text/plain', buffer: after,
  });
  const response = page.waitForResponse(result =>
    result.url().endsWith('/api/revision-pairs') && result.request().method() === 'POST');
  await form.getByRole('button', { name: '保存并查看差异', exact: true }).click();
  const imported = await response;
  expect(imported.ok()).toBeTruthy();
  const result = await imported.json();
  expect(result.originals[0].sha256).toBe(createHash('sha256').update(before).digest('hex'));
  expect(result.originals[1].sha256).toBe(createHash('sha256').update(after).digest('hex'));
  expect(result.originals.every((original: { date: string; reviewer_role: string }) =>
    original.date === '2026-11-19' && original.reviewer_role === 'collaborator')).toBeTruthy();
  const evidence = page.getByRole('region', { name: '修改前后差异依据', exact: true });
  await expect(evidence.getByLabel('修改前后差异')).toContainText('-Assume $x \\le y$.');
  await expect(evidence.getByLabel('修改前后差异'))
    .toContainText('+Assume $x \\le y$, under the stated condition.');
  await expect(evidence.getByRole('heading', { name: '修改前：synthetic-browser-before.tex' }))
    .toBeVisible();
  await expect(evidence.getByRole('heading', { name: '修改后：synthetic-browser-after.tex' }))
    .toBeVisible();
  await expect(form.getByText('已保存原稿、修订稿和差异；没有自动建立规则。', { exact: true }))
    .toBeVisible();
  expect(await (await request.get('/api/rules')).json()).toEqual(rulesBefore);
  expect(await (await request.get('/api/proposals')).json()).toEqual(proposalsBefore);
  expect((await (await request.get('/api/sync')).json()).commit).toBe(commitBefore);
  await page.reload();
  await page.getByRole('button', { name: '来源与意见', exact: true }).click();
  const archive = page.getByRole('button').filter({ hasText: 'revision-diff.txt' })
    .filter({ hasText: 'synthetic-pair-browser' });
  await expect(archive).toHaveCount(1);
  await archive.click();
  await expect(evidence.getByLabel('修改前后差异')).toContainText(result.diff);
  const stored = await (await request.get('/api/revision-pairs/' + result.diff_source)).json();
  expect(stored).toEqual(result);
  await page.screenshot({
    path: test.info().outputPath('windows-revision-pair-evidence.png'), fullPage: true,
  });
});
