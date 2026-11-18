import { test, expect } from '@playwright/test';

test('paper workspace imports, displays, and exports a structured review without approving rules',
  async ({ page, request }) => {
    const suffix = Date.now().toString();
    const paperId = 'synthetic-review-paper-' + suffix;
    const ruleId = 'R-SYNTHETIC-REVIEW-' + suffix;
    const reviewId = 'REV-SYNTHETIC-' + suffix;
    const paper = await request.post('/api/papers', {
      data: { paper_id: paperId, title: 'Synthetic report paper' },
    });
    expect(paper.ok()).toBeTruthy();
    const created = await request.post('/api/proposals', { data: { rule: {
      id: ruleId, short_title: 'Synthetic review guidance',
      statement: 'Explain the synthetic assumptions.',
      scope: { paper_ids: [paperId], sections: ['proof'] },
    } } });
    expect(created.ok()).toBeTruthy();
    const proposal = await created.json();
    const approved = await request.post('/api/proposals/' + proposal.proposal_id + '/approve', {
      data: { proposal_hash: proposal.proposal_hash },
    });
    expect(approved.ok()).toBeTruthy();
    const rulesBefore = await (await request.get('/api/rules')).json();
    const report = {
      review_id: reviewId, paper_id: paperId, section: 'proof',
      task_summary: 'Synthetic browser review report', provider: 'external',
      model: 'synthetic-review-fixture', source: 'synthetic-browser-test',
      findings: [{
        rule_id: ruleId, rule_version: 1, location: 'synthetic.tex:4',
        quote: 'Synthetic claim without assumptions.',
        description: 'Synthetic reviewer finding.',
        evidence: 'Synthetic assumptions are absent in this excerpt.',
        recommendation: 'State the synthetic assumptions before this claim.',
        review_type: 'semantic',
      }],
      unresolved: ['Synthetic derivation needs human confirmation.'],
    };
    await page.goto('/');
    await page.getByRole('button', { name: '论文工作区', exact: true }).click();
    await page.getByLabel('选择已保存论文', { exact: true }).selectOption(paperId);
    await page.getByLabel('导入结构化审查 JSON', { exact: true }).fill(JSON.stringify(report));
    await page.getByRole('button', { name: '保存审查报告', exact: true }).click();
    await expect(page.getByText('审查报告已保存，生效规则没有改变。', { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Synthetic browser review report', exact: true })).toBeVisible();
    await expect(page.getByText('Synthetic claim without assumptions.', { exact: true })).toBeVisible();
    await expect(page.getByText('Synthetic derivation needs human confirmation.', { exact: true })).toBeVisible();
    await expect(page.getByText('这份报告没有逐条检查记录，无法据此确认哪些规则已经检查。', { exact: true })).toBeVisible();
    const jsonURL = await page.getByRole('link', { name: '导出审查 JSON', exact: true }).getAttribute('href');
    const downloaded = await request.get(jsonURL!);
    expect(downloaded.ok()).toBeTruthy();
    expect((await downloaded.json()).findings[0].rule_id).toBe(ruleId);
    const markdownURL = await page.getByRole('link', { name: '导出审查 Markdown', exact: true }).getAttribute('href');
    const markdown = await request.get(markdownURL!);
    expect(markdown.ok()).toBeTruthy();
    expect(await markdown.text()).toContain('Synthetic reviewer finding.');
    expect(await (await request.get('/api/rules')).json()).toEqual(rulesBefore);
    await page.reload();
    await page.getByRole('button', { name: '论文工作区', exact: true }).click();
    await page.getByLabel('选择已保存论文', { exact: true }).selectOption(paperId);
    await expect(page.getByRole('heading', { name: 'Synthetic browser review report', exact: true })).toBeVisible();
    const detailed = {
      ...report,
      review_id: reviewId + '-COVERAGE',
      task_summary: 'Synthetic coverage evidence report',
      memory_commit: (await (await request.get('/api/sync')).json()).commit,
      memory_rules_dirty: false,
      rule_snapshot: rulesBefore.filter((rule: { id: string }) => rule.id === ruleId),
      diff_mode: true,
      semantic_status: 'not_reviewed',
      latex_build_status: 'not_run',
      coverage: [{
        rule_id: ruleId, rule_version: 1, status: 'unavailable',
        checked_line_count: 0, reason: 'semantic_not_reviewed',
      }],
      files: [{
        path: 'synthetic.tex', sha256: '0'.repeat(64),
        diff: ['-Synthetic old claim.', '+Synthetic claim without assumptions.'].join(String.fromCharCode(10)),
      }],
      fixed_items: ['Synthetic fixed item recorded by the report author.'],
    };
    await page.getByLabel('导入结构化审查 JSON', { exact: true }).fill(JSON.stringify(detailed));
    await page.getByRole('button', { name: '保存审查报告', exact: true }).click();
    await expect(page.getByRole('heading', { name: detailed.task_summary, exact: true })).toBeVisible();
    const evidence = page.getByRole('region', { name: '审查范围与版本依据', exact: true });
    await expect(evidence.getByText('报告列出 1 条规则：已执行 0 条，未审查 0 条，无法执行 1 条。', { exact: true })).toBeVisible();
    await expect(evidence.getByText('输入范围：变更区域', { exact: true })).toBeVisible();
    await expect(evidence.getByText('语义审查：未审查；LaTeX 构建：未运行', { exact: true })).toBeVisible();
    await evidence.getByText('查看 1 条历史规则快照', { exact: true }).click();
    await expect(evidence.getByText('Explain the synthetic assumptions.', { exact: true })).toBeVisible();
    await evidence.getByText('查看 synthetic.tex 的修改对比', { exact: true }).click();
    await expect(evidence.locator('pre')).toContainText('+Synthetic claim without assumptions.');
    await expect(evidence.getByText(detailed.fixed_items[0], { exact: true })).toBeVisible();
    expect(await (await request.get('/api/rules')).json()).toEqual(rulesBefore);
  });
