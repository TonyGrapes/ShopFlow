// Vitest config — отдельный от vite.config.ts, чтобы не путать dev-build
// с тестами. Переиспользует тот же react-плагин.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // Cast: the installed tree has two vite copies — top-level 7.x (rolldown
   // types) and a nested one under vitest (rollup types). @vitejs/plugin-react
   // is resolved from the top-level copy, while defineConfig expects the
   // nested copy's Plugin type. Runtime is fine (both implement Rollup's
   // plugin interface); only the type identity differs. See TS2769.
   // Remove this cast once vite/plugin-react/vitest versions are aligned
   // (see the TODO below).
   plugins: [react() as any],
   test: {
     globals: true,
     environment: 'jsdom',
     setupFiles: './src/test/setup.ts',
     coverage: {
       provider: 'v8',
       all: true,
       reporter: ['text', 'html', 'lcov'],
       reportsDirectory: './coverage',
       exclude: [
         '**/node_modules/**',
         '**/dist/**',
         '**/*.config.{js,ts,mjs,cjs}',
         '**/*.d.ts',
         'src/main.tsx',
         'src/**/*.test.{ts,tsx}',
         'src/test/**',
         'src/types/**',
         'src/**/types.ts',
         'src/prototypes/**',
       ],
       thresholds: {
         // Baseline 10.77% (21 tests / ~3000 stmts). Fix the fact now,
         // ratchet  2 per epic in the same PR that adds the tests.
         // branches/functions are not gated yet: v8 reports misleadingly
         // high values (uncalled functions show 100% branch — see
         // vitest-dev/vitest#2390). Enable them once lines >= 40%.
         lines: 10,
       },
     },
   },
 })