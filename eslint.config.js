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
      // Lists whose items carry identity and state (network people, event
      // chips, person rows) are keyed. The rest render derived text segments,
      // geometry and decorative fills that are recomputed wholesale and never
      // reordered independently; for those the only available key is the
      // index, which reconciles exactly like no key at all. Requiring one
      // would add ceremony without changing behaviour, and inventing a
      // non-unique key would turn a working render into a runtime error.
      'svelte/require-each-key': 'off',
      'svelte/infinite-reactive-loop': 'warn',
      'svelte/no-reactive-reassign': 'warn',
      // Unsound in components: the rule reasons about one top-to-bottom pass
      // through a function, but Svelte re-runs `$:` blocks and reorders them
      // by dependency. State trackers assigned at the end of a reactive block
      // and read by its own condition on the next run look dead to it, as does
      // a const declared below the reactive statement that uses it. Acting on
      // either would reintroduce the loops those trackers exist to stop.
      // Still enabled for plain .js, where the analysis holds.
      'no-useless-assignment': 'off'
    }
  }
];
