import js from "@eslint/js";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import prettierConfig from "eslint-config-prettier";

export default [
  js.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsparser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: {
        window: "readonly",
        document: "readonly",
        console: "readonly",
        fetch: "readonly",
        URL: "readonly",
        URLSearchParams: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        requestAnimationFrame: "readonly",
        cancelAnimationFrame: "readonly",
        HTMLElement: "readonly",
        HTMLInputElement: "readonly",
        HTMLTextAreaElement: "readonly",
        HTMLSelectElement: "readonly",
        HTMLDivElement: "readonly",
        MouseEvent: "readonly",
        KeyboardEvent: "readonly",
        Event: "readonly",
        FileReader: "readonly",
        Blob: "readonly",
        FormData: "readonly",
        AbortController: "readonly",
        Response: "readonly",
        Headers: "readonly",
        Map: "readonly",
        Set: "readonly",
        Promise: "readonly",
        ResizeObserver: "readonly",
        IntersectionObserver: "readonly",
        MutationObserver: "readonly",
        CustomEvent: "readonly",
        DOMParser: "readonly",
        Worker: "readonly",
        structuredClone: "readonly",
        crypto: "readonly",
        performance: "readonly",
        navigator: "readonly",
        location: "readonly",
        history: "readonly",
        localStorage: "readonly",
        sessionStorage: "readonly",
        alert: "readonly",
        confirm: "readonly",
      },
    },
    plugins: {
      "@typescript-eslint": tseslint,
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...tseslint.configs.recommended.rules,
      // Spread react-hooks recommended, then override compiler to warn
      ...Object.fromEntries(
        Object.entries(reactHooks.configs.recommended.rules).map(
          ([key, val]) => [key, Array.isArray(val) && val[0] === 2 ? ["warn", ...val.slice(1)] : val === 2 ? "warn" : val]
        )
      ),
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // Lenient for existing code — downgrade errors to warnings
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      "@typescript-eslint/no-empty-object-type": "warn",
      "no-unused-vars": "off",
      "no-undef": "off", // TypeScript handles this
      "no-case-declarations": "warn",
      "no-useless-assignment": "warn",
      "react-hooks/rules-of-hooks": "warn",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
  prettierConfig,
  {
    ignores: ["dist/", "node_modules/", "*.config.js", "*.config.ts"],
  },
];
