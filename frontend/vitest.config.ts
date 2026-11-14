// Vitest config — отдельный от vite.config.ts, чтобы не путать dev-build
// с тестами. Переиспользует тот же react-плагин.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,        // CSS Modules → proxy-объекты, тесты не завязаны на классы
    include: ["src/**/*.test.{ts,tsx}"],
    // Не подхватываем backend и node_modules
    exclude: ["**/node_modules/**", "**/dist/**"],
  },
});