import js from '@eslint/js';
import globals from 'globals';
import svelte from 'eslint-plugin-svelte';
import prettier from 'eslint-config-prettier/flat';

export default [
  {
    // Flat config resolves ignores per linted file rather than from the cwd,
    // so nested checkouts must be excluded explicitly.
    ignores: [
      'node_modules/',
      'dist/',
      'build/',
      '.svelte-kit/',
      '.claude/',
      '.venv/',
      'data/people/**/_cache/',
      '*.config.js',
      '*.config.cjs',
      'pmtiles.exe',
      '*.log',
      '*.tmp',
      'temp_*.json'
    ]
  },
  js.configs.recommended,
  ...svelte.configs.recommended,
  prettier,
  ...svelte.configs.prettier,
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node
      }
    },
    rules: {
      'no-console': 'off',
      'no-debugger': 'warn',
      // ESLint 9 flipped the caughtErrors default from 'none' to 'all', which
      // newly flags unused catch bindings. Warn rather than error until those
      // are cleaned up.
      'no-unused-vars': ['warn', {
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
    }
  },
  {
    files: ['**/*.svelte'],
    rules: {
      // Static site with trusted content
      'svelte/no-at-html-tags': 'off',
      'svelte/no-unused-svelte-ignore': 'warn',
      'svelte/valid-compile': 'warn',
      'no-inner-declarations': 'off'
    }
  },
  // Rules newly enabled as errors by ESLint 10 and eslint-plugin-svelte 3.
  // Downgraded to warnings so the toolchain upgrade did not turn ~97
  // pre-existing findings into build failures; each is worth fixing on its own.
  {
    rules: {
      'no-useless-assignment': 'warn'
    }
  },
  {
    files: ['**/*.svelte'],
    rules: {
      'svelte/require-each-key': 'warn',
      'svelte/infinite-reactive-loop': 'warn',
      'svelte/no-reactive-reassign': 'warn'
    }
  }
];
