// eslint 9 flat-config template — SonarQube "Sonar way" parity for Node.js + TypeScript.
// Dev dependencies required in the target repo:
//   npm install --save-dev eslint @eslint/js eslint-plugin-sonarjs typescript-eslint
// Adjust QUALITY_COGNITIVE_MAX parity by changing the threshold below (default 15).
import js from "@eslint/js";
import sonarjs from "eslint-plugin-sonarjs";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "node_modules/**",
      "dist/**",
      "build/**",
      "coverage/**",
      "vendor/**",
    ],
  },
  js.configs.recommended,
  sonarjs.configs.recommended,
  // @typescript-eslint recommended rules, scoped to TypeScript files only.
  ...tseslint.configs.recommended.map((config) => ({
    ...config,
    files: ["**/*.ts", "**/*.tsx"],
  })),
  {
    rules: {
      "sonarjs/cognitive-complexity": ["error", 15],
    },
  },
);
