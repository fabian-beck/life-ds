module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true
  },
  parserOptions: {
    ecmaVersion: 2022,
    sourceType: 'module'
  },
  extends: [
    'eslint:recommended',
    'prettier'
  ],
  plugins: ['svelte'],
  overrides: [
    {
      files: ['*.svelte'],
      parser: 'svelte-eslint-parser',
      parserOptions: {
        parser: null
      },
      rules: {
        'svelte/no-at-html-tags': 'off', // Static site with trusted content
        'svelte/no-unused-svelte-ignore': 'warn',
        'svelte/valid-compile': 'warn',
        'no-inner-declarations': 'off'
      }
    }
  ],
  rules: {
    'no-console': 'off',
    'no-debugger': 'warn',
    'no-unused-vars': ['error', {
      argsIgnorePattern: '^_',
      varsIgnorePattern: '^_',
      caughtErrorsIgnorePattern: '^_'
    }],
    'no-undef': 'error',
    'no-var': 'error',
    'prefer-const': 'error',
    'prefer-arrow-callback': 'warn',
    'eqeqeq': ['error', 'always', { null: 'ignore' }],
    'no-eval': 'error',
    'no-implied-eval': 'error',
    'no-new-func': 'error',
    'no-return-await': 'warn',
    'require-await': 'warn',
    'no-await-in-loop': 'warn',
    'no-promise-executor-return': 'warn',
    'no-template-curly-in-string': 'warn',
    'no-unreachable-loop': 'warn'
  },
  ignorePatterns: [
    'node_modules/',
    'dist/',
    'build/',
    '.svelte-kit/',
    'data/people/**/_cache/',
    '*.config.js',
    '*.config.cjs'
  ]
};
