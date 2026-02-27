import nextPlugin from "eslint-config-next";

/** @type {import("eslint").Linter.Config[]} */
const config = [
  {
    ignores: ["dist/**", ".next/**"],
  },
  nextPlugin,
];

export default config;

