import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:8000',
    browserName: 'chromium',
    channel: process.env.STUDIO_BROWSER_CHANNEL || undefined,
    trace: 'retain-on-failure',
  },
  webServer: {
    command:
      process.platform === 'win32'
        ? '..\\.venv\\Scripts\\puzzlepress-studio.exe --books ../books --frontend dist'
        : '../.venv/bin/puzzlepress-studio --books ../books --frontend dist',
    url: 'http://127.0.0.1:8000/api/projects',
    reuseExistingServer: !process.env.CI,
    timeout: 15000,
  },
});
