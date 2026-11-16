import { defineConfig } from '@playwright/test';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

process.env.PAPERRULE_E2E_TOKEN ??= randomUUID();

export default defineConfig({
  testDir: './e2e',
  outputDir: '../.test-tmp/playwright-results',
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  expect: { timeout: 10000 },
  reporter: [['list']],
  globalTeardown: './e2e/teardown.ts',
  use: { baseURL: 'http://127.0.0.1:18765', trace: 'retain-on-failure' },
  webServer: {
    command: (process.env.PAPERRULE_TEST_PYTHON ?? 'python') + ' scripts/e2e_server.py',
    cwd: path.resolve(import.meta.dirname, '..'),
    url: 'http://127.0.0.1:18765/api/health',
    reuseExistingServer: false,
    timeout: 30000,
    env: {
      PAPERRULE_E2E_TOKEN: process.env.PAPERRULE_E2E_TOKEN,
      PYTHONPATH: path.resolve(import.meta.dirname, '../src'),
      PYTHONDONTWRITEBYTECODE: '1',
      TEMP: path.resolve(import.meta.dirname, '../.test-tmp'),
      TMP: path.resolve(import.meta.dirname, '../.test-tmp'),
    },
  },
});
