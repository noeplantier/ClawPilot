const js = require("@eslint/js");
const react = require("eslint-plugin-react");
const reactHooks = require("eslint-plugin-react-hooks");

module.exports = [
  js.configs.recommended,
  {
    files: ["src/**/*.{js,jsx}"],
    plugins: { react, "react-hooks": reactHooks },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: {
        window: "readonly", document: "readonly", localStorage: "readonly", console: "readonly",
        process: "readonly", fetch: "readonly", navigator: "readonly",
        setTimeout: "readonly", clearTimeout: "readonly", setInterval: "readonly", clearInterval: "readonly",
        URL: "readonly", URLSearchParams: "readonly",
      },
    },
    settings: { react: { version: "detect" } },
    rules: {
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      "react/prop-types": "off",
      "react/react-in-jsx-scope": "off",
      // This codebase renders literal "//" as decorative UI text (mono-accent
      // terminal styling), not stray JS comments — this rule's false-positive
      // rate here is too high to be useful.
      "react/jsx-no-comment-textnodes": "off",
      // cmdk (Radix command palette) sets a custom `cmdk-input-wrapper` DOM attribute.
      "react/no-unknown-property": ["error", { ignore: ["cmdk-input-wrapper"] }],
      "no-unused-vars": "warn",
    },
  },
  {
    // Jest globals for the unit tests that live next to the code.
    files: ["src/**/*.test.{js,jsx}", "src/setupTests.js"],
    languageOptions: {
      globals: {
        describe: "readonly", it: "readonly", test: "readonly", expect: "readonly", jest: "readonly",
        beforeEach: "readonly", afterEach: "readonly", beforeAll: "readonly", afterAll: "readonly", global: "readonly", Event: "readonly",
      },
    },
  },
];
