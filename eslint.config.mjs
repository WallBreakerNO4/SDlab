import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Additional ignores:
    ".open-next/**",
    "dist/**",
    ".sisyphus/**",
    ".wrangler/**",
    "types/routes.d.ts",
    "types/validator.ts",
  ]),
  // Extracted hooks from virtual-grid.tsx inherit the same patterns that were
  // originally covered by "use no memo" in that file. The React Compiler ESLint
  // rules for refs-in-render and setState-in-effect flag these intentional
  // patterns; suppress them for these modules since the patterns are documented
  // and tested in the parent component.
  {
    files: ["components/comfyui/use-virtual-grid-layout.ts"],
    rules: {
      "react-hooks/refs": "off",
    },
  },
  {
    files: ["components/comfyui/virtual-grid-cell-dialog.tsx"],
    rules: {
      "react-hooks/set-state-in-effect": "off",
    },
  },
]);

export default eslintConfig;
