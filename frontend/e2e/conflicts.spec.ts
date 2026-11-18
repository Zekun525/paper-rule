import { test, expect } from '@playwright/test';

test('paper workspace exposes approved conflicts without automatically resolving either rule',
  async ({ page, request }) => {
    const suffix = Date.now().toString();
    const paperId = 'synthetic-conflict-paper-' + suffix;
    const firstId = 'R-SYNTHETIC-CONFLICT-A-' + suffix;
    const secondId = 'R-SYNTHETIC-CONFLICT-B-' + suffix;
    const firstTitle = 'Synthetic first conflicting guidance ' + suffix;
    expect((await request.post('/api/papers', {
      data: { paper_id: paperId, title: 'Synthetic conflict paper ' + suffix },
    })).ok()).toBeTruthy();
    const secondResponse = await request.post('/api/proposals', { data: { rule: {
      id: secondId, short_title: 'Synthetic second conflicting guidance ' + suffix,
      statement: 'State synthetic assumptions after the synthetic claim.',
      scope: { paper_ids: [paperId] },
    } } });
    expect(secondResponse.ok()).toBeTruthy();
    const second = await secondResponse.json();
    expect((await request.post('/api/proposals/' + second.proposal_id + '/approve', {
      data: { proposal_hash: second.proposal_hash },
    })).ok()).toBeTruthy();
    const baseline = await (await request.get('/api/rules')).json();
    const firstResponse = await request.post('/api/proposals', { data: { rule: {
      id: firstId, short_title: firstTitle,
      statement: 'State synthetic assumptions before the synthetic claim.',
      scope: { paper_ids: [paperId] },
    } } });
    expect(firstResponse.ok()).toBeTruthy();
    expect(await (await request.get('/api/rules')).json()).toEqual(baseline);
    const before = await request.post('/api/context', {
      data: { paper_id: paperId, section: 'proof', task: 'revise' },
    });
    expect(before.ok()).toBeTruthy();
    expect((await before.json()).unresolved_conflicts).toEqual([]);

    await page.goto('/');
    await page.getByRole('button', { name: '审批中心', exact: true }).click();
    await page.getByRole('button').filter({ hasText: firstTitle }).click();
    await page.getByRole('button', { name: '直接修改提案', exact: true }).click();
    await page.getByRole('button', { name: '添加规则关系', exact: true }).click();
    await page.getByLabel('关系目标规则编号', { exact: true }).fill(secondId);
    await page.getByLabel('关系状态', { exact: true }).selectOption('approved');
    await page.getByRole('button', { name: '保存待审批版本', exact: true }).click();
    await expect(page.getByRole('button', { name: '批准当前第 2 版', exact: true })).toBeVisible();
    expect(await (await request.get('/api/rules')).json()).toEqual(baseline);
    await page.getByRole('button', { name: '批准当前第 2 版', exact: true }).click();
    await expect(page.getByText('已生效 · 第 2 版 · ' + firstId, { exact: true })).toBeVisible();
    const approved = await (await request.get('/api/rules')).json();
    for (const rule of baseline) {
      expect(approved.find((item: { id: string }) => item.id === rule.id)).toEqual(rule);
    }
    await page.getByRole('button', { name: '论文工作区', exact: true }).click();
    await page.getByLabel('选择已保存论文', { exact: true }).selectOption(paperId);
    await page.getByLabel('章节', { exact: true }).fill('proof');
    await page.getByRole('button', { name: '加载适用规则', exact: true }).click();
    await expect(page.getByRole('heading', {
      name: '存在尚未解决的规则冲突', exact: true,
    })).toBeVisible();
    const warning = page.getByRole('alert').filter({ hasText: '规则上下文不完整' });
    await expect(warning).toContainText(firstId);
    await expect(warning).toContainText(secondId);
    await expect(warning).not.toContainText('以下必需规则尚未加载：。');
    expect(await (await request.get('/api/rules')).json()).toEqual(approved);
    await page.getByRole('button', { name: '前往审批中心处理规则关系', exact: true }).click();
    await expect(page.getByRole('heading', { name: '审批中心', exact: true })).toBeVisible();
    const firstActive = approved.find((item: { id: string }) => item.id === firstId);
    expect(firstActive).toBeTruthy();
    const resolutionTitle = firstTitle + ' resolution';
    const resolution = await request.post('/api/proposals', { data: {
      operation: 'amend', rule: { ...firstActive, short_title: resolutionTitle },
    } });
    expect(resolution.ok()).toBeTruthy();
    await page.getByRole('button', { name: '刷新数据', exact: true }).click();
    await page.getByRole('button').filter({ hasText: resolutionTitle }).click();
    await page.getByRole('button', { name: '直接修改提案', exact: true }).click();
    await page.getByRole('button', { name: '移除第 1 条关系', exact: true }).click();
    await page.getByLabel('规则内容', { exact: true }).fill(
      'State synthetic assumptions after the synthetic claim.',
    );
    await page.getByRole('button', { name: '保存待审批版本', exact: true }).click();
    await expect(page.getByRole('button', { name: '批准当前第 2 版', exact: true })).toBeVisible();
    expect(await (await request.get('/api/rules')).json()).toEqual(approved);
    const stillConflicted = await request.post('/api/context', {
      data: { paper_id: paperId, section: 'proof', task: 'revise' },
    });
    expect((await stillConflicted.json()).unresolved_conflicts).toHaveLength(1);
    await page.getByRole('button', { name: '批准当前第 2 版', exact: true }).click();
    await expect(page.getByText('已生效 · 第 2 版 · ' + firstId, { exact: true })).toBeVisible();
    const resolved = await (await request.get('/api/rules')).json();
    for (const rule of baseline) {
      expect(resolved.find((item: { id: string }) => item.id === rule.id)).toEqual(rule);
    }
    const revised = resolved.find((item: { id: string }) => item.id === firstId);
    expect(revised.version).toBe(2);
    expect(revised.relations).toEqual([]);
    const finalContext = await request.post('/api/context', {
      data: { paper_id: paperId, section: 'proof', task: 'revise' },
    });
    const bundle = await finalContext.json();
    expect(bundle.unresolved_conflicts).toEqual([]);
    expect(bundle.complete).toBe(true);
    await page.getByRole('button', { name: '论文工作区', exact: true }).click();
    await page.getByLabel('选择已保存论文', { exact: true }).selectOption(paperId);
    await page.getByLabel('章节', { exact: true }).fill('proof');
    await page.getByRole('button', { name: '加载适用规则', exact: true }).click();
    await expect(page.getByText('规则快照：' + bundle.memory_commit, { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: '存在尚未解决的规则冲突', exact: true })).toHaveCount(0);
  });
