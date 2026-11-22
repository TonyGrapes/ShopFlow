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
        // Ratchet history:
        //   H.1 (21 tests):  10.77% -> threshold 10
        //   H.2 (adds 34):   ~19-21% (labels / debounce / async / toast)
        //                    -> threshold 12, 2 as planned.
        // Next ratchet (H.3: auth context  api layer) targets 14;
        // by H.5 we should reach ~30, at which point we can start
        // gating branches/functions (v8 reports misleadingly high
        // branch% for uncalled code, see vitest-dev/vitest#2390).
        lines: 12,
       },
     },
   },
 })