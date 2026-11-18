import { test, expect } from '@playwright/test';

test('owner link establishes a real browser session and protects mutations',
  async ({ browser }) => {
    const context = await browser.newContext({
      baseURL: 'http://127.0.0.1:18765', extraHTTPHeaders: {},
    });
    try {
      expect((await context.request.get('/api/rules')).status()).toBe(401);
      const page = await context.newPage();
      await page.goto('/');
      await expect(page.getByRole('heading', { name: 'PaperRule 本机访问' })).toBeVisible();
      const token = process.env.PAPERRULE_E2E_TOKEN;
      expect(token).toBeTruthy();
      await page.goto('/#owner_token=' + token);
      await expect(page.getByRole('button', { name: '论文工作区', exact: true })).toBeVisible();
      expect(new URL(page.url()).hash).toBe('');
      const cookies = await context.cookies();
      const owner = cookies.find(cookie => cookie.name === 'paperrule_owner');
      expect(owner?.httpOnly).toBe(true);
      expect(owner?.sameSite).toBe('Strict');
      expect((await context.request.get('/api/rules')).ok()).toBeTruthy();
      const paperId = 'synthetic-session-paper-' + Date.now();
      expect((await context.request.post('/api/papers', {
        data: { paper_id: paperId, title: 'Unauthorized synthetic paper' },
      })).status()).toBe(403);
      await page.getByRole('button', { name: '论文工作区', exact: true }).click();
      await page.getByLabel('论文编号', { exact: true }).fill(paperId);
      await page.getByLabel('论文标题', { exact: true }).fill('Synthetic owner session paper');
      await page.getByLabel('研究类型', { exact: true }).fill('synthetic-theory');
      await page.getByLabel('投稿期刊', { exact: true }).fill('SYNTHETIC');
      await page.getByLabel('文章类型', { exact: true }).fill('full');
      await page.getByRole('button', { name: '保存论文档案', exact: true }).click();
      await expect(page.getByText('论文档案已保存。预览将使用保存后的投稿目标和文章类型。')).toBeVisible();
      const papers = await (await context.request.get('/api/papers')).json();
      expect(papers.find((paper: { paper_id: string }) => paper.paper_id === paperId)?.title)
        .toBe('Synthetic owner session paper');
      await page.reload();
      await expect(page.getByRole('button', { name: '论文工作区', exact: true })).toBeVisible();
    } finally {
      await context.close();
    }
  });
