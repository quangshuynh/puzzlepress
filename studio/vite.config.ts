import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { copyFileSync } from 'node:fs';

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'existing-puzzlepress-logo',
      closeBundle() {
        copyFileSync('../docs/images/puzzlepress-logo.png', 'dist/logo.png');
      },
    },
  ],
  server: { proxy: { '/api': 'http://127.0.0.1:8000', '/logo.png': 'http://127.0.0.1:8000' } },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.tsx'],
  },
});
