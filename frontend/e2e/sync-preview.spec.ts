import { test, expect } from '@playwright/test';

test.use({ viewport: { width: 1280, height: 960 } });

test('Windows displays real divergent Git versions and clears stale preview after failure',
  async ({ page, request }, testInfo) => {
    test.setTimeout(120000);
    const headers = { 'X-Test-Token': process.env.PAPERRULE_E2E_TOKEN ?? '' };
    try {
      const prepared = await request.post('/__e2e/sync-fixture', { headers, timeout: 60000 });
      expect(prepared.ok()).toBeTruthy();
      const seeded = await prepared.json();
      const before = await (await request.get('/api/rules')).json();
      const proposalsBefore = await (await request.get('/api/proposals')).json();
      const commitBefore = (await (await request.get('/api/sync')).json()).commit;
      await page.goto('/');
      await page.getByRole('button', { name: '设置与诊断', exact: true }).click();
      const preview = page.getByRole('region', { name: '跨电脑规则差异预览', exact: true });
      const read = preview.getByRole('button', { name: '读取三方规则差异', exact: true });
      await expect(read).toBeEnabled();
      const responsePromise = page.waitForResponse(response =>
        response.url().endsWith('/api/sync/preview') && response.request().method() === 'POST');
      await read.click();
      const response = await responsePromise;
      expect(response.ok()).toBeTruthy();
      const result = await response.json();
      expect(result.base_commit).toBe(seeded.base_commit);
      expect(result.local_commit).toBe(seeded.local_commit);
      expect(result.remote_commit).toBe(seeded.remote_commit);
      await expect(preview.getByText('两边都修改过，需要逐条核对', { exact: true })).toBeVisible();
      const change = preview.getByRole('article', { name: '规则差异 ' + seeded.rule_id, exact: true });
      const base = change.getByRole('region', { name: '共同版本', exact: true });
      const local = change.getByRole('region', { name: '本机版本', exact: true });
      const remote = change.getByRole('region', { name: '远端版本', exact: true });
      await expect(base.getByText(seeded.base_statement, { exact: true })).toBeVisible();
      await expect(local.getByText(seeded.local_statement, { exact: true })).toBeVisible();
      await expect(remote.getByText(seeded.remote_statement, { exact: true })).toBeVisible();
      for (const version of [base, local, remote]) {
        await expect(version).toContainText(seeded.paper_id);
        await expect(version).toContainText('proof');
        await expect(version).toContainText('Synthetic exception retained for comparison.');
      }
      await expect(page.locator('script').filter({ hasText: 'syntheticSyncExecuted' })).toHaveCount(0);
      expect(await page.evaluate(() => 'syntheticSyncExecuted' in globalThis)).toBe(false);
      await preview.getByText('查看这次预览的版本依据', { exact: true }).click();
      await expect(preview).toContainText(result.preview_sha256);
      await remote.getByText('查看这版规则的完整记录与校验值', { exact: true }).click();
      await expect(remote.locator('pre')).toContainText(seeded.remote_statement);
      const width = await page.evaluate(() => ({
        content: document.documentElement.scrollWidth,
        viewport: document.documentElement.clientWidth,
      }));
      expect(width.content).toBeLessThanOrEqual(width.viewport);
      expect(await (await request.get('/api/rules')).json()).toEqual(before);
      expect(await (await request.get('/api/proposals')).json()).toEqual(proposalsBefore);
      expect((await (await request.get('/api/sync')).json()).commit).toBe(commitBefore);
      await page.screenshot({
        path: testInfo.outputPath('windows-real-sync-preview.png'), fullPage: true,
      });
      await page.getByRole('button', { name: '重新检查状态', exact: true }).click();
      await expect(change).toHaveCount(0);
      await read.click();
      await expect(change).toBeVisible();
      expect((await request.post('/__e2e/sync-fixture/cleanup', { headers })).ok()).toBeTruthy();
      const unavailable = page.waitForResponse(item =>
        item.url().endsWith('/api/sync/preview') && item.request().method() === 'POST');
      await read.click();
      expect((await unavailable).status()).toBe(400);
      await expect(change).toHaveCount(0);
      await expect(page.getByRole('alert')).toContainText('私有远端');
      expect(await (await request.get('/api/rules')).json()).toEqual(before);
    } finally {
      const detached = await request.post('/__e2e/sync-fixture/cleanup', { headers });
      expect(detached.ok()).toBeTruthy();
    }
  });
