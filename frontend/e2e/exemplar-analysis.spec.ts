import { test, expect } from '@playwright/test';

test.use({ viewport: { width: 1440, height: 1000 } });

function syntheticExemplarPDF(): Buffer {
  const newline = String.fromCharCode(10);
  const open = String.fromCharCode(60, 60);
  const streams = [
    ['BT', '/F1 12 Tf', '72 720 Td', '(Synthetic abstract.) Tj', 'ET'].join(newline),
    [
      'BT', '/F1 12 Tf', '72 720 Td', '(Introduction) Tj', '0 -20 Td',
      '(Existing synthetic methods assume independent samples.) Tj', 'ET',
    ].join(newline),
  ];
  const page = (content: number) => open + ' /Type /Page /Parent 2 0 R '
    + '/MediaBox [0 0 600 800] /Resources ' + open + ' /Font '
    + open + ' /F1 7 0 R >> >> /Contents ' + content + ' 0 R >>';
  const objects = [
    open + ' /Type /Catalog /Pages 2 0 R >>',
    open + ' /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>',
    page(5), page(6),
    ...streams.map(content => open + ' /Length ' + Buffer.byteLength(content, 'ascii')
      + ' >>' + newline + 'stream' + newline + content + newline + 'endstream'),
    open + ' /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ];
  let document = '%PDF-1.4' + newline;
  const offsets: number[] = [];
  objects.forEach((body, index) => {
    offsets.push(Buffer.byteLength(document, 'ascii'));
    document += (index + 1) + ' 0 obj' + newline + body + newline + 'endobj' + newline;
  });
  const xref = Buffer.byteLength(document, 'ascii');
  document += [
    'xref', '0 8', '0000000000 65535 f ',
    ...offsets.map(offset => String(offset).padStart(10, '0') + ' 00000 n '),
    'trailer', open + ' /Size 8 /Root 1 0 R >>', 'startxref', String(xref), '%%EOF', '',
  ].join(newline);
  return Buffer.from(document, 'ascii');
}

test('Windows exemplar UI shows a synthetic suggestion with real PDF page evidence and no approval',
  async ({ page, request }, testInfo) => {
    const rulesBefore = await (await request.get('/api/rules')).json();
    const proposalsBefore = await (await request.get('/api/proposals')).json();
    const commitBefore = (await (await request.get('/api/sync')).json()).commit;
    const filename = 'synthetic-exemplar-ui-' + Date.now() + '.pdf';
    const focus = '学习引言如何组织已有工作和研究空缺';
    const quote = 'Existing synthetic methods assume independent samples.';
    await page.goto('/');
    await page.getByRole('button', { name: '来源与意见', exact: true }).click();
    await page.getByText('填写来源、论文和日期（可选）', { exact: true }).click();
    await page.getByRole('combobox', { name: '用途', exact: true }).selectOption('exemplar');
    await page.getByLabel('学习目标 / 来源说明', { exact: true }).fill(focus);
    const importPromise = page.waitForResponse(response =>
      response.url().endsWith('/api/sources') && response.request().method() === 'POST');
    await page.getByLabel('上传材料').setInputFiles({
      name: filename, mimeType: 'application/pdf', buffer: syntheticExemplarPDF(),
    });
    const importedResponse = await importPromise;
    expect(importedResponse.ok()).toBeTruthy();
    const imported = await importedResponse.json();
    const source = imported.source;
    expect(source.kind).toBe('exemplar');
    expect(source.intent).toBe(focus);
    expect(imported.feedback).toHaveLength(2);
    const item = imported.feedback.find((row: { location: { page: number } }) =>
      row.location.page === 2);
    expect(item.quote).toContain(quote);
    expect(item.location.page_index).toBe(1);
    const adapted = 'In this fictional setting, we identify a baseline assumption before describing the specific gap.';
    const limitations = 'This illustrates writing structure only and does not establish a universal rule or a verified research claim.';
    const fixture = {
      analysis_id: 'AN-SYNTHETIC-EXEMPLAR-UI', created_at: '2026-11-19T00:00:00Z',
      status: 'suggested', stale: false, provider: 'synthetic-ui-fixture',
      model: 'synthetic-exemplar-model', prompt_version: 'feedback-analysis-v2',
      error: null, classification_confirmed: false, proposal_created: false,
      candidate_rules: [],
      suggestion: {
        classification: 'exemplar', explanation: 'Synthetic fixture illustrates a baseline-to-gap transition.',
        rule: null, related_rules: [],
        example: {
          title: 'Synthetic introduction writing example', focus, section: 'introduction',
          page: 2, quote, writing_feature: 'Introduce the baseline before explaining its limitation.',
          adapted_example: adapted, limitations,
          source_id: source.id, source_sha256: source.sha256,
          feedback_id: item.id, feedback_sha256: item.sha256,
          source_location: item.location, human_review: 'pending', mandatory_rule: false,
        },
      },
    };
    // Only the AI analysis is a marked synthetic fixture. PDF import, extraction,
    // stored-source preview and all rule/proposal state checks use the actual backend.
    // This test does not establish successful real inference or model quality.
    await page.route('**/api/feedback/' + item.id + '/analyses', async route => {
      if (route.request().method() === 'POST') {
        expect(route.request().postDataJSON().expected_sha256).toBe(item.sha256);
        await route.fulfill({ json: fixture });
      } else {
        await route.fulfill({ json: [fixture] });
      }
    });
    await page.getByRole('button', {
      name: new RegExp(filename.replaceAll('.', '[.]')),
    }).click();
    const card = page.locator('article.evidence').filter({
      has: page.getByText(item.quote, { exact: true }),
    });
    await expect(card).toHaveCount(1);
    await card.getByRole('button', { name: '请求 AI 整理', exact: true }).click();
    const example = page.getByRole('region', { name: '范文写作案例', exact: true });
    await expect(example.getByRole('heading', {
      name: 'Synthetic introduction writing example', exact: true,
    })).toBeVisible();
    await expect(example.getByText('学习目标：' + focus, { exact: true })).toBeVisible();
    await expect(example.getByText('原文位置：introduction · 第 2 页', { exact: true })).toBeVisible();
    await expect(example.getByText(quote, { exact: true })).toBeVisible();
    await expect(example.getByText(adapted, { exact: true })).toBeVisible();
    await expect(example.getByText('适用限制：' + limitations, { exact: true })).toBeVisible();
    await expect(card.getByRole('button', { name: '编辑 AI 建议草稿', exact: true })).toHaveCount(0);
    await example.getByText('查看案例来源依据', { exact: true }).click();
    const preview = example.getByRole('img', { name: '范文案例所在原始 PDF 页面', exact: true });
    await preview.scrollIntoViewIfNeeded();
    await expect(preview).toBeVisible();
    await expect.poll(async () => preview.evaluate((image: HTMLImageElement) =>
      image.complete && image.naturalWidth > 0)).toBe(true);
    await expect(example.getByText('原件 SHA-256：' + source.sha256, { exact: true })).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath('windows-synthetic-exemplar-page-evidence.png'), fullPage: true,
    });
    const feedback = await (await request.get('/api/feedback')).json();
    expect(feedback.find((row: { id: string }) => row.id === item.id)).toEqual(item);
    expect(await (await request.get('/api/rules')).json()).toEqual(rulesBefore);
    expect(await (await request.get('/api/proposals')).json()).toEqual(proposalsBefore);
    expect((await (await request.get('/api/sync')).json()).commit).toBe(commitBefore);
  });
