import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:8015',
    browserName: 'chromium',
    channel: process.env.STUDIO_BROWSER_CHANNEL || undefined,
    trace: 'retain-on-failure',
  },
  webServer: {
    command:
      process.platform === 'win32'
        ? '..\\.venv\\Scripts\\python.exe e2e/server.py'
        : '../.venv/bin/python e2e/server.py',
    url: 'http://127.0.0.1:8015/api/projects',
    reuseExistingServer: false,
    timeout: 15000,
  },
});
