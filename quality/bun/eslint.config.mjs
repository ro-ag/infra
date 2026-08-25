// eslint 9 flat config — SonarQube "Sonar way" parity for Bun + TypeScript.
// Requires devDependencies: eslint, @eslint/js, typescript-eslint,
// eslint-plugin-sonarjs (install: bun add -d eslint @eslint/js typescript-eslint eslint-plugin-sonarjs)
import js from "@eslint/js";
import sonarjs from "eslint-plugin-sonarjs";
import tseslint from "typescript-eslint";

export default [
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/build/**",
      "**/coverage/**",
    ],
  },
  js.configs.recommended,
  sonarjs.configs.recommended,
  ...tseslint.configs.recommended.map((config) => ({
    files: ["**/*.ts", "**/*.tsx"],
    ...config,
  })),
  {
    // sonarjs plugin is already registered by sonarjs.configs.recommended.
    files: ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx"],
    rules: {
      "sonarjs/cognitive-complexity": ["error", 15],
    },
  },
];
