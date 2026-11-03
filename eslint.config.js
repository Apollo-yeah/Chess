/**
 * ESLint 扁平配置（ESLint 9+ 要求；旧的 .eslintrc.js 在 "type": "module" 下完全失效）。
 *
 * 目标：守住 React Hooks 规则（规则违反是运行时 bug，编译期不会报），
 * 顺带查未使用变量与未定义全局，无需新增任何依赖。
 */
import reactHooks from 'eslint-plugin-react-hooks';

const browserGlobals = {
  window: 'readonly',
  document: 'readonly',
  navigator: 'readonly',
  location: 'readonly',
  localStorage: 'readonly',
  sessionStorage: 'readonly',
  console: 'readonly',
  fetch: 'readonly',
  WebSocket: 'readonly',
  URL: 'readonly',
  URLSearchParams: 'readonly',
  AbortController: 'readonly',
  setTimeout: 'readonly',
  clearTimeout: 'readonly',
  setInterval: 'readonly',
  clearInterval: 'readonly',
  requestAnimationFrame: 'readonly',
  cancelAnimationFrame: 'readonly',
  alert: 'readonly',
  confirm: 'readonly',
  performance: 'readonly',
  structuredClone: 'readonly',
};

export default [
  {
    ignores: ['web/dist/**', 'node_modules/**', 'app/static/**'],
  },
  {
    files: ['web/src/**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: browserGlobals,
    },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'no-undef': 'error',
      'no-const-assign': 'error',
      'no-dupe-keys': 'error',
      'no-unreachable': 'error',
    },
  },
];
