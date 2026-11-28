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
        //   H.4 (adds 16; AuthProvider 100%): 23.46% -> threshold 18
        //   H.5 (adds 29; CartProvider/FavoritesProvider 100%): 27.31% -> threshold 25
        //   H.6 (adds 32; LoginPage 100%, CartPage ~98%): 30.41% -> threshold 28
        //   H.7 (adds 29; Orders/Product 100%): 38.86% -> threshold 36
        //   Cleanup: removed unused src/pages/CatalogPage (100% covered).
        //     38.86% -> 36.20% (smaller denominator, lower average) -> 34.
        //   H.8a (adds 37; catalog utils 100%, hooks ~93%): 39.88% -> 37
        //   H.8b (adds 15; features/catalog ~99%): 54.86% -> 52
        //   H.9 (adds 19; CheckoutPage 99%, AddressForm 100%): 62.30% -> 59
        //   H.10 (adds 13; OrderDetailPage 100%): 65.99% -> 63
        //   H.11 (adds 14; RegisterPage 184/187): 69.10% -> 66
        // Next: admin/remaining pages. Branch/function gates deferred (v8 odd
        // numbers for uncalled code, vitest-dev/vitest#2390).
        lines: 66,
       },
     },
   },
 })