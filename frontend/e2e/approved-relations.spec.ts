import { test, expect } from '@playwright/test';

test('Windows approval shows source evidence and pinned targets before local override selection',
  async ({ page, request }) => {
    const suffix = Date.now().toString();
    const firstPaper = 'synthetic-local-a-' + suffix;
    const otherPaper = 'synthetic-local-b-' + suffix;
    const parentId = 'R-SYNTHETIC-PARENT-' + suffix;
    const childId = 'R-SYNTHETIC-LOCAL-' + suffix;
    const childTitle = 'Synthetic local exception ' + suffix;
    const originalQuote = 'Explain the synthetic assumption where it is used.';
    const parentStatement = 'State synthetic assumptions before the synthetic claim.';
    for (const paper of [firstPaper, otherPaper]) {
      expect((await request.post('/api/papers', {
        data: { paper_id: paper, title: 'Synthetic relationship paper ' + paper },
      })).ok()).toBeTruthy();
    }
    const imported = await request.post('/api/sources', { data: {
      filename: 'synthetic-related-source.txt',
      content_base64: Buffer.from(originalQuote, 'utf8').toString('base64'),
      reviewer_id: 'synthetic-senior-' + suffix, reviewer_role: 'senior',
      paper_id: firstPaper, date: '2026-11-19',
    } });
    expect(imported.ok()).toBeTruthy();
    const evidenceId = (await imported.json()).feedback[0].id;
    const parentResponse = await request.post('/api/proposals', { data: { rule: {
      id: parentId, short_title: 'Synthetic general guidance ' + suffix,
      statement: parentStatement, source_feedback_ids: [evidenceId],
      scope: { levels: ['paper'], paper_ids: [firstPaper, otherPaper] },
    } } });
    expect(parentResponse.ok()).toBeTruthy();
    const parent = await parentResponse.json();
    expect((await request.post('/api/proposals/' + parent.proposal_id + '/approve', {
      data: { proposal_hash: parent.proposal_hash },
    })).ok()).toBeTruthy();
    const baseline = await (await request.get('/api/rules')).json();
    const baselineCommit = (await (await request.get('/api/sync')).json()).commit;
    const childResponse = await request.post('/api/proposals', { data: { rule: {
      id: childId, short_title: childTitle,
      statement: 'Explain the synthetic local assumption next to its application.',
      scope: { levels: ['paper'], paper_ids: [firstPaper] },
      relations: [{ type: 'exception_to', target_id: parentId, status: 'approved' }],
    } } });
    expect(childResponse.ok()).toBeTruthy();
    const child = await childResponse.json();
    const pin = child.after.relations[0];
    expect(pin.target_version).toBe('1');
    expect(pin.target_sha256).toMatch(/^[a-f0-9]{64}$/);
    await page.goto('/');
    await page.getByRole('button', { name: '审批中心', exact: true }).click();
    await page.getByRole('button').filter({ hasText: childTitle }).click();
    const preview = page.getByRole('region', { name: '规则关系目标 ' + childId, exact: true });
    await expect(preview.getByText('本版提案绑定的目标：' + parentId + ' · v1',
      { exact: true })).toBeVisible();
    await expect(preview).toContainText(parentStatement);
    await expect(preview).toContainText(originalQuote);
    await preview.getByText('查看目标内容校验值', { exact: true }).click();
    await expect(preview.getByText(pin.target_sha256, { exact: true })).toBeVisible();
    expect(await (await request.get('/api/rules')).json()).toEqual(baseline);
    expect((await (await request.get('/api/sync')).json()).commit).toBe(baselineCommit);
    await page.screenshot({
      path: test.info().outputPath('windows-target-binding-preview.png'), fullPage: true,
    });
    await page.getByRole('button', { name: '批准当前第 1 版', exact: true }).click();
    await expect(page.getByText('已生效 · 第 1 版 · ' + childId, { exact: true })).toBeVisible();
    const approved = await (await request.get('/api/rules')).json();
    const currentParent = approved.find((rule: { id: string }) => rule.id === parentId);
    expect(currentParent).toEqual(baseline.find((rule: { id: string }) => rule.id === parentId));
    await page.getByRole('button', { name: '论文工作区', exact: true }).click();
    await page.getByLabel('选择已保存论文', { exact: true }).selectOption(firstPaper);
    await page.getByLabel('章节', { exact: true }).fill('proof');
    await page.getByRole('button', { name: '加载适用规则', exact: true }).click();
    const explanation = page.getByRole('region', { name: '本次适用的已批准关系', exact: true });
    await expect(explanation).toContainText(childId);
    await expect(explanation).toContainText(parentId);
    await expect(explanation).toContainText('本次采用了明确批准的例外规则');
    const local = await (await request.post('/api/context', {
      data: { paper_id: firstPaper, section: 'proof', task: 'revise' },
    })).json();
    expect(local.rules.some((entry: { rule: { id: string } }) => entry.rule.id === childId))
      .toBeTruthy();
    expect(local.rules.some((entry: { rule: { id: string } }) => entry.rule.id === parentId))
      .toBeFalsy();
    const other = await (await request.post('/api/context', {
      data: { paper_id: otherPaper, section: 'proof', task: 'revise' },
    })).json();
    expect(other.rules.some((entry: { rule: { id: string } }) => entry.rule.id === parentId))
      .toBeTruthy();
    expect(other.rules.some((entry: { rule: { id: string } }) => entry.rule.id === childId))
      .toBeFalsy();
    expect(await (await request.get('/api/rules')).json()).toEqual(approved);
    await page.screenshot({
      path: test.info().outputPath('windows-local-rule-selection.png'), fullPage: true,
    });
    const manuscriptForm = page.getByRole('region', { name: '发起论文审查', exact: true });
    await manuscriptForm.getByLabel('稿件文件名', { exact: true }).fill('synthetic-relations.tex');
    await manuscriptForm.getByLabel('稿件原文', { exact: true }).fill(
      'Synthetic assumption and its synthetic local application.',
    );
    await manuscriptForm.getByLabel('本次审查章节', { exact: true }).fill('proof');
    await manuscriptForm.getByLabel('本次审查任务', { exact: true }).fill('revise');
    await expect(manuscriptForm.getByRole('checkbox')).not.toBeChecked();
    const reviewResponsePromise = page.waitForResponse(response =>
      response.url().endsWith('/api/reviews/check') && response.request().method() === 'POST');
    await manuscriptForm.getByRole('button', {
      name: '开始审查并保存报告', exact: true,
    }).click();
    const reviewResponse = await reviewResponsePromise;
    expect(reviewResponse.ok()).toBeTruthy();
    expect(reviewResponse.request().postDataJSON().send_to_provider).toBe(false);
    const review = await reviewResponse.json();
    expect(review.rule_snapshot.some((rule: { id: string }) => rule.id === parentId)).toBeFalsy();
    expect(review.rule_snapshot.some((rule: { id: string }) => rule.id === childId)).toBeTruthy();
    const selectionBasis = page.getByRole('region', { name: '本次规则选择依据', exact: true });
    await expect(selectionBasis).toContainText(parentId);
    await expect(selectionBasis).toContainText(childId);
    await expect(selectionBasis).toContainText('已批准的局部例外');
    expect((await (await request.get('/api/reviews/' + review.review_id + '/report')).json())
      .selection_notes).toEqual(review.selection_notes);
    expect(await (await request.get('/api/rules')).json()).toEqual(approved);
    await page.screenshot({
      path: test.info().outputPath('windows-review-rule-selection.png'), fullPage: true,
    });
    const amendmentResponse = await request.post('/api/proposals', { data: {
      operation: 'amend', rule: {
        ...currentParent, statement: 'Explain the revised synthetic general assumption.',
      },
    } });
    expect(amendmentResponse.ok()).toBeTruthy();
    const amendment = await amendmentResponse.json();
    expect((await request.post('/api/proposals/' + amendment.proposal_id + '/approve', {
      data: { proposal_hash: amendment.proposal_hash },
    })).ok()).toBeTruthy();
    const revised = await (await request.get('/api/rules')).json();
    await page.getByRole('button', { name: '加载适用规则', exact: true }).click();
    const warning = page.getByRole('alert').filter({ hasText: '规则上下文不完整' });
    await expect(warning).toContainText('目标规则已更新，原关系需要重新核对和审批。');
    await expect(warning).toContainText(childId);
    await expect(warning).toContainText(parentId);
    expect(await (await request.get('/api/rules')).json()).toEqual(revised);
  });
