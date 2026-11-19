import { test, expect } from '@playwright/test';
import { randomUUID } from 'node:crypto';

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

test('Windows regression explains approved local replacements using actual stored cases',
  async ({ page, request }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 960 });
    const suffix = randomUUID();
    const firstPaper = 'SYNTHETIC-REGRESSION-A-' + suffix;
    const otherPaper = 'SYNTHETIC-REGRESSION-B-' + suffix;
    const parentId = 'R-SYNTHETIC-GENERAL-' + suffix;
    const childId = 'R-SYNTHETIC-LOCAL-' + suffix;
    const localOldCase = 'CASE-SYNTHETIC-LOCAL-OLD-' + suffix;
    const localNewCase = 'CASE-SYNTHETIC-LOCAL-NEW-' + suffix;
    const otherCase = 'CASE-SYNTHETIC-OTHER-' + suffix;
    for (const paperId of [firstPaper, otherPaper]) {
      expect((await request.post('/api/papers', { data: {
        paper_id: paperId, title: 'Synthetic regression paper ' + paperId,
      } })).ok()).toBeTruthy();
    }
    for (const rule of [
      {
        id: parentId, short_title: 'Synthetic general regression guidance',
        statement: 'avoid: synthetic old phrase', check_method: 'deterministic',
        scope: { levels: ['paper'], paper_ids: [firstPaper, otherPaper] },
        relations: [],
      },
      {
        id: childId, short_title: 'Synthetic local regression guidance',
        statement: 'avoid: synthetic new phrase', check_method: 'deterministic',
        scope: { levels: ['paper'], paper_ids: [firstPaper] },
        relations: [{ type: 'exception_to', target_id: parentId, status: 'approved' }],
      },
    ]) {
      const created = await request.post('/api/proposals', { data: { rule } });
      expect(created.ok()).toBeTruthy();
      const proposal = await created.json();
      expect((await request.post('/api/proposals/' + proposal.proposal_id + '/approve', {
        data: { proposal_hash: proposal.proposal_hash },
      })).ok()).toBeTruthy();
    }
    const rulesBefore = await (await request.get('/api/rules')).json();
    const commitBefore = (await (await request.get('/api/sync')).json()).commit;
    for (const item of [
      { id: localOldCase, rule_id: parentId, paper_id: firstPaper },
      { id: localNewCase, rule_id: childId, paper_id: firstPaper },
      { id: otherCase, rule_id: parentId, paper_id: otherPaper },
    ]) {
      expect((await request.post('/api/regression/cases', { data: {
        ...item, rule_version: 1, check_method: 'deterministic',
        input_text: 'synthetic old phrase and synthetic new phrase',
        expected: 'violation', explanation: 'Synthetic labeled relationship acceptance case.',
      } })).ok()).toBeTruthy();
    }
    await page.goto('/');
    await page.getByRole('button', { name: '回归测试', exact: true }).click();
    const responsePromise = page.waitForResponse(response =>
      response.url().endsWith('/api/regression/runs') && response.request().method() === 'POST');
    await page.getByRole('button', { name: '运行已保存案例', exact: true }).click();
    const response = await responsePromise;
    expect(response.ok()).toBeTruthy();
    const report = await response.json();
    const replaced = report.results.find((item: { id: string }) => item.id === localOldCase);
    expect(replaced.status).toBe('unavailable');
    expect(replaced.reason).toBe('rule_replaced_in_context');
    expect(replaced.passed).toBeNull();
    expect(replaced.paper_profile_snapshot.paper_id).toBe(firstPaper);
    expect(replaced.selection_rules.some((rule: { rule_id: string }) =>
      rule.rule_id === childId)).toBe(true);
    for (const caseId of [localNewCase, otherCase]) {
      expect(report.results.find((item: { id: string }) => item.id === caseId).passed).toBe(true);
    }
    const results = page.locator('details').filter({ hasText: localOldCase })
      .filter({ has: page.getByText('逐项结果', { exact: true }) });
    await results.getByText('逐项结果', { exact: true }).click();
    const basis = page.getByRole('region', {
      name: '本次案例规则选择依据 ' + localOldCase, exact: true,
    });
    await expect(basis).toContainText(parentId);
    await expect(basis).toContainText(childId);
    await expect(basis).toContainText('已批准的局部例外');
    await expect(results.getByText(
      localOldCase + '：未检查 本次范围已采用获批的替代规则，此旧规则案例未执行',
      { exact: true },
    )).toBeVisible();
    await expect(results.getByText(otherCase + '：通过', { exact: true })).toBeVisible();
    const replacedRow = basis.locator('..');
    await replacedRow.getByText('查看本次检查的输入、规则和校验记录', { exact: true }).click();
    await expect(replacedRow.locator('pre')).toContainText(firstPaper);
    await expect(replacedRow.locator('pre')).toContainText(childId);
    await expect(replacedRow.locator('pre')).toContainText('paper_profile_sha256');
    const pageWidth = await page.evaluate(() => ({
      content: document.documentElement.scrollWidth,
      viewport: document.documentElement.clientWidth,
    }));
    expect(pageWidth.content).toBeLessThanOrEqual(pageWidth.viewport);
    const exported = await request.get('/api/regression/runs/' + report.run_id + '/report');
    expect(exported.ok()).toBeTruthy();
    expect(await exported.json()).toEqual(report);
    expect(await (await request.get('/api/rules')).json()).toEqual(rulesBefore);
    expect((await (await request.get('/api/sync')).json()).commit).toBe(commitBefore);
    await page.screenshot({
      path: testInfo.outputPath('windows-regression-approved-selection.png'), fullPage: true,
    });
  });
