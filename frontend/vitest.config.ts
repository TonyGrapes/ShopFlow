// Vitest config — отдельный от vite.config.ts, чтобы не путать dev-build
// с тестами. Переиспользует тот же react-плагин.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // vite 7 + @vitejs/plugin-react 5.2 + vitest 3 resolve to a single vite
  // copy, so plugin-react's Plugin type matches vitest/config's — no cast.
  plugins: [react()],
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
        //   H.2 (adds 34):   ~19-21% -> threshold 12
        //   H.3 (adds 86; src/api 99%): 21.81% -> threshold 16
        // Next: context/AuthProvider, catalog components, pages.
        // At ~30% start gating branches/functions (v8 quirk for
        // uncalled code, see vitest-dev/vitest#2390).
        lines: 16,
       },
     },
   },
 })