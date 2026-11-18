import { test, expect } from '@playwright/test';

test('regression history displays synthetic model evidence and preserves legacy results',
  async ({ page, request }) => {
    const rulesBefore = await (await request.get('/api/rules')).json();
    const syntheticRun = {
      run_id: 'RUN-SYNTHETIC-DISPLAY', status: 'incomplete',
      total: 2, passed: 1, failed: 0, unavailable: 1,
      created_at: '2026-11-18T00:00:00Z',
      results: [
        {
          id: 'CASE-SYNTHETIC-JUDGMENT', status: 'passed',
          provider: 'scripted-display-fixture', model: 'synthetic-display-model',
          prompt_version: 'regression-semantic-v1', human_review: 'pending',
          judgment: {
            verdict: 'violation', explanation: 'Synthetic excerpt uses an undefined symbol.',
            quote: 'The value of x increases.',
          },
          input_sha256: '1'.repeat(64), rule_sha256: '2'.repeat(64),
          case_sha256: '3'.repeat(64),
          case_snapshot: { input_text: 'The value of x increases.', expected: 'violation' },
          rule_snapshot: { id: 'R-SYNTHETIC-DISPLAY', version: 1,
            statement: 'Define synthetic symbols before use.' },
        },
        {
          id: 'CASE-SYNTHETIC-INVALID', status: 'unavailable',
          reason: 'semantic_response_invalid',
        },
      ],
    };
    // This response fixture checks rendering only; it is not a live model evaluation.
    await page.route('**/api/regression/runs', async route => {
      if (route.request().method() !== 'GET') {
        await route.continue();
        return;
      }
      await route.fulfill({
        json: [syntheticRun, {
          run_id: 'RUN-SYNTHETIC-LEGACY', status: 'passed',
          total: 1, passed: 1, failed: 0, unavailable: 0,
          created_at: '2026-11-17T00:00:00Z',
          results: [{ id: 'CASE-SYNTHETIC-LEGACY', status: 'passed' }],
        }],
      });
    });
    await page.goto('/');
    await page.getByRole('button', { name: '回归测试', exact: true }).click();
    await expect(page.getByText('2 个案例：1 通过，0 失败，1 未检查')).toBeVisible();
    await page.getByText('逐项结果', { exact: true }).first().click();
    await expect(page.getByText('AI 判定：发现问题', { exact: true })).toBeVisible();
    await expect(page.getByText('Synthetic excerpt uses an undefined symbol.',
      { exact: true })).toBeVisible();
    await expect(page.getByRole('blockquote')).toHaveText('The value of x increases.');
    await expect(page.getByText('服务：scripted-display-fixture · 模型：synthetic-display-model · 待人工核对',
      { exact: true })).toBeVisible();
    await expect(page.getByText(/AI 回复未通过校验，此案例未完成检查/)).toBeVisible();
    await page.getByText('查看本次检查的输入、规则和校验记录', { exact: true }).click();
    await expect(page.locator('pre')).toContainText('Define synthetic symbols before use.');
    await expect(page.locator('pre')).toContainText('1'.repeat(64));
    await page.getByText('逐项结果', { exact: true }).last().click();
    await expect(page.getByText('CASE-SYNTHETIC-LEGACY：通过', { exact: true })).toBeVisible();
    expect(await (await request.get('/api/rules')).json()).toEqual(rulesBefore);
  });
