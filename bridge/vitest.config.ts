import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['bridge/tests/**/*.test.mjs'],
    coverage: {
      provider: 'v8',
      include: ['bridge/index.mjs'],
      reporter: ['text', 'json', 'html'],
    },
  },
});
