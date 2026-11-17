// ESLint — только для React-специфичных проверок, которые oxlint 1.71
// не покрывает (rules-of-hooks на module-scope, exhaustive-deps).
// oxlint остаётся основным линтером (быстрее, 104 правила);
// ESLint запускается в CI как отдельный шаг.
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

export default [
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      // oxlint уже ловит эти — не дублируем шумом
      "@typescript-eslint/no-unused-vars": "off",
      "no-unused-vars": "off",
      "no-undef": "off",
    },
    languageOptions: {
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
      globals: {
        window: "readonly",
        document: "readonly",
        localStorage: "readonly",
        fetch: "readonly",
        crypto: "readonly",
        URL: "readonly",
        URLSearchParams: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        FormData: "readonly",
      },
    },
  },
  {
    files: ["src/**/*.test.{ts,tsx}"],
    languageOptions: {
      globals: {
        describe: "readonly",
        it: "readonly",
        expect: "readonly",
        vi: "readonly",
        beforeEach: "readonly",
        afterEach: "readonly",
      },
    },
  },
    {
    ignores: [
      "dist/**",
      "node_modules/**",
      "coverage/**",
      // Legacy-прототипы: не входят в прод, в .gitignore.
      // Содержат eslint-disable-комментарии для oxlint-правил
      // (react/only-export-components и т.п.), которых в ESLint нет.
      "src/prototypes/**",
    ],
  },
];