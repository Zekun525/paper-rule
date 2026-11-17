import { test, expect } from '@playwright/test';

test('restore previews every changed rule and applies only after explicit approval',
  async ({ page, request }) => {
    const suffix = Date.now().toString();
    async function createRule(id: string) {
      const response = await request.post('/api/proposals', { data: { rule: {
        id, short_title: 'Synthetic restore guidance ' + id,
        statement: 'Preserve synthetic restoration evidence.',
      } } });
      expect(response.ok()).toBeTruthy();
      const proposal = await response.json();
      const approval = await request.post('/api/proposals/' + proposal.proposal_id + '/approve', {
        data: { proposal_hash: proposal.proposal_hash },
      });
      expect(approval.ok()).toBeTruthy();
    }
    await createRule('R-SYNTHETIC-RESTORE-ANCHOR-' + suffix);
    const target = (await (await request.get('/api/sync')).json()).commit;
    const unchanged = await (await request.get('/api/rules')).json();
    const later = ['R-SYNTHETIC-RESTORE-B-' + suffix, 'R-SYNTHETIC-RESTORE-C-' + suffix];
    for (const id of later) await createRule(id);
    const baseline = await (await request.get('/api/rules')).json();
    const oldCommit = (await (await request.get('/api/sync')).json()).commit;
    await page.goto('/');
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click();
    await page.getByRole('combobox', { name: '选择规则历史版本', exact: true }).selectOption(target);
    await page.getByRole('button', { name: '预览恢复内容', exact: true }).click();
    await expect(page.getByRole('heading', { name: '本次恢复涉及 2 条规则', exact: true })).toBeVisible();
    expect(await (await request.get('/api/rules')).json()).toEqual(baseline);
    await page.getByRole('button', { name: '创建恢复提案并前往审批', exact: true }).click();
    await expect(page.getByRole('heading', { name: '本次提案包含 2 条规则', exact: true })).toBeVisible();
    const fullProposal = page.getByRole('region', { name: '完整提案内容', exact: true });
    for (const id of later) await expect(fullProposal.getByRole('heading', { name: id, exact: false })).toBeVisible();
    expect(await (await request.get('/api/rules')).json()).toEqual(baseline);
    await page.getByRole('button', { name: '批准当前第 1 版', exact: true }).click();
    await expect(page.getByText('已生效 · 第 1 版 ·', { exact: false })).toBeVisible();
    const result = await (await request.get('/api/rules')).json();
    for (const rule of unchanged) expect(result.find((item: { id: string }) => item.id === rule.id)).toEqual(rule);
    for (const id of later) {
      const rule = result.find((item: { id: string }) => item.id === id);
      expect(rule.status).toBe('deprecated');
      expect(rule.version).toBe(2);
    }
    expect((await (await request.get('/api/sync')).json()).commit).not.toBe(oldCommit);
  });
