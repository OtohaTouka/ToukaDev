// eslint.config.mjs — ESLint 9+ flat config
// 用 .mjs 副檔名確保無論 package.json 的 "type" 為何，一律以 ESM 解析。
// 安裝：npm install --save-dev eslint @eslint/js globals
import js from "@eslint/js";
import globals from "globals";

// TypeScript 專案：npm install --save-dev typescript-eslint，並取消下方註解：
// import tseslint from "typescript-eslint";
// React 專案：npm install --save-dev eslint-plugin-react eslint-plugin-react-hooks，並取消下方註解：
// import react from "eslint-plugin-react";
// import reactHooks from "eslint-plugin-react-hooks";

export default [
  js.configs.recommended,
  // TypeScript 專案取消下方註解：
  // ...tseslint.configs.recommended,
  // React 專案取消下方註解：
  // react.configs.flat.recommended,
  // reactHooks.configs["recommended-latest"],
  {
    files: ["**/*.{js,mjs,cjs,jsx,ts,tsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      "no-unused-vars": "error",
      "no-console": "warn",
      "no-var": "error",
      "prefer-const": "error",
      eqeqeq: ["error", "always"],
      "no-implicit-globals": "error",
    },
  },
  {
    ignores: ["node_modules/", "dist/", "build/", "coverage/", ".venv/"],
  },
];
