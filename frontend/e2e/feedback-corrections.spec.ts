import { test, expect } from '@playwright/test';

function syntheticBlankPDF(): Buffer {
  const newline = String.fromCharCode(10);
  const objects = [
    '1 0 obj' + newline + '<< /Type /Catalog /Pages 2 0 R >>' + newline + 'endobj',
    '2 0 obj' + newline + '<< /Type /Pages /Kids [3 0 R] /Count 1 >>' + newline + 'endobj',
    '3 0 obj' + newline +
      '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>' + newline + 'endobj',
  ];
  let document = '%PDF-1.4' + newline;
  const offsets: number[] = [];
  for (const object of objects) {
    offsets.push(Buffer.byteLength(document, 'ascii'));
    document += object + newline;
  }
  const xref = Buffer.byteLength(document, 'ascii');
  document += [
    'xref', '0 4', '0000000000 65535 f ',
    ...offsets.map(offset => String(offset).padStart(10, '0') + ' 00000 n '),
    'trailer', '<< /Size 4 /Root 1 0 R >>', 'startxref', String(xref), '%%EOF', '',
  ].join(newline);
  return Buffer.from(document, 'ascii');
}

test('manual transcription and corrections preserve originals without approving rules',
  async ({ page, request }) => {
    const rulesBefore = await (await request.get('/api/rules')).json();
    const commitBefore = (await (await request.get('/api/sync')).json()).commit;
    await page.goto('/');
    await page.getByRole('button', { name: '来源与意见', exact: true }).click();
    await page.getByLabel('来源代号', { exact: true }).fill('synthetic-manual-reviewer');
    await page.getByRole('combobox', { name: '用途', exact: true }).selectOption('annotated_pdf');
    const importedResponse = page.waitForResponse(response =>
      response.url().endsWith('/api/sources') && response.request().method() === 'POST');
    await page.getByLabel('上传材料').setInputFiles({
      name: 'synthetic-manual-scan.pdf', mimeType: 'application/pdf',
      buffer: syntheticBlankPDF(),
    });
    const imported = await importedResponse;
    expect(imported.ok()).toBeTruthy();
    const source = (await imported.json()).source;
    expect(source.extraction_status).toBe('pending_transcription');
    await page.getByRole('button', { name: /synthetic-manual-scan.pdf/ }).click();
    const transcription = page.getByRole('region', { name: '原件人工补录', exact: true });
    await transcription.getByLabel('补录原文', { exact: true })
      .fill('Synthetic manually transcribed original feedback.');
    await transcription.getByLabel('补录原因', { exact: true })
      .fill('Synthetic blank PDF needs manual transcription.');
    await transcription.getByLabel('确认来源角色', { exact: true })
      .fill('synthetic-custom-reviewer');
    await transcription.getByLabel('原件页码（未知可留空）', { exact: true }).fill('1');
    await transcription.getByLabel('章节或位置说明', { exact: true }).fill('synthetic-proof');
    const transcribedResponse = page.waitForResponse(response =>
      response.url().endsWith('/transcriptions') && response.request().method() === 'POST');
    await transcription.getByRole('button', { name: '保存人工补录', exact: true }).click();
    const transcribed = await transcribedResponse;
    expect(transcribed.ok()).toBeTruthy();
    const item = await transcribed.json();
    expect(item.source_id).toBe(source.id);
    expect(item.reviewer_id).toBe('synthetic-manual-reviewer');
    expect(item.reviewer_role).toBe('synthetic-custom-reviewer');
    expect(item.location.page_index).toBe(0);
    await expect(page.getByText('已保存人工补录，原件和提取状态均保留。',
      { exact: true })).toBeVisible();
    await expect(page.getByText(item.quote, { exact: true })).toBeVisible();
    await page.getByText('补充解释或纠错', { exact: true }).click();
    await page.getByLabel('修正或补充的解释', { exact: true })
      .fill('Synthetic clarification: move these two paragraphs only in this paper.');
    await page.getByLabel('修正依据', { exact: true })
      .fill('Synthetic reviewer confirmed this is a one-off edit.');
    await page.getByLabel('补充确认分类', { exact: true }).selectOption('one_off_edit');
    await page.getByRole('button', { name: '追加纠错记录', exact: true }).click();
    await expect(page.getByText('已追加纠错记录，原话和生效规则均未改动。',
      { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '据此创建提案', exact: true })).toBeDisabled();
    await expect(page.getByText('当前确认分类：当前论文的一次性修改',
      { exact: true })).toBeVisible();
    await expect(page.getByText(item.quote, { exact: true })).toBeVisible();
    const stored = (await (await request.get('/api/feedback')).json())
      .find((feedback: { id: string }) => feedback.id === item.id);
    expect(stored.quote).toBe(item.quote);
    expect(stored.source_id).toBe(source.id);
    expect(stored.corrections).toHaveLength(1);
    expect(stored.corrections[0].classification).toBe('one_off_edit');
    expect(stored.corrections[0].previous_sha256).toBe(item.sha256);
    const storedSource = (await (await request.get('/api/sources')).json())
      .find((record: { id: string }) => record.id === source.id);
    expect(storedSource.sha256).toBe(source.sha256);
    expect(storedSource.extraction_status).toBe('pending_transcription');
    expect(await (await request.get('/api/rules')).json()).toEqual(rulesBefore);
    expect((await (await request.get('/api/sync')).json()).commit).toBe(commitBefore);
    await page.reload();
    await page.getByRole('button', { name: '来源与意见', exact: true }).click();
    await page.getByRole('button', { name: /synthetic-manual-scan.pdf/ }).click();
    await expect(page.getByText(item.quote, { exact: true })).toBeVisible();
    await expect(page.getByText('当前确认分类：当前论文的一次性修改',
      { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '据此创建提案', exact: true })).toBeDisabled();
  });
