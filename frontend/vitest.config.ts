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
        //   H.12 (adds 18; AdminProductsPage 100%): 73.82% -> 71
        //   H.13 (adds 15; AdminUsersPage 100%): 77.20% -> 74
        //   H.14 (adds 9; AdminOrdersPage + shared Pagination 100%): 79.50% -> 77
        //   H.15 (adds 11; AdminCategoriesPage 100%): 81.43% -> 79
        //   H.16 (adds 20; Dashboard/RevenueChart/AdminLayout/Toast 100%): 83.68% -> 81
        //   H.17 (adds 15; ProfilePage 100%): 86.97% -> 84
        //   H.18 (adds 14; AddressesPage/AddressForm 100%): 89.51% -> 86
        // Next: VerifyEmail + app shell/guards. Branch/function gates deferred (v8 odd
        // numbers for uncalled code, vitest-dev/vitest#2390).
        lines: 86,
       },
     },
   },
 })