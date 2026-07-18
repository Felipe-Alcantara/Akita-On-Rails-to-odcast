"use strict";

const js = require("@eslint/js");

const readonly = "readonly";

module.exports = [
  {
    ignores: ["node_modules/**"],
  },
  js.configs.recommended,
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "commonjs",
      globals: {
        Buffer: readonly,
        __dirname: readonly,
        clearInterval: readonly,
        clearTimeout: readonly,
        console: readonly,
        module: readonly,
        process: readonly,
        require: readonly,
        setInterval: readonly,
        setTimeout: readonly,
      },
    },
    rules: {
      "no-constant-binary-expression": "error",
      "no-duplicate-imports": "error",
      "no-promise-executor-return": "error",
      "no-self-compare": "error",
      "no-template-curly-in-string": "error",
      "no-unmodified-loop-condition": "error",
      "no-unused-vars": ["error", { argsIgnorePattern: "^_", caughtErrors: "none" }],
      "no-useless-assignment": "error",
      "prefer-const": "error",
    },
  },
  {
    files: ["renderer/**/*.js"],
    languageOptions: {
      globals: {
        alert: readonly,
        confirm: readonly,
        document: readonly,
        window: readonly,
      },
    },
  },
];
