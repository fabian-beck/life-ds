module.exports = {
  extends: ["stylelint-config-standard"],
  rules: {
    "color-hex-length": "long",
    "color-named": "never",
    "no-descending-specificity": null,
    "declaration-empty-line-before": null,
    "selector-pseudo-class-no-unknown": [
      true,
      {
        ignorePseudoClasses: ["global"],
      },
    ],
    "selector-type-no-unknown": [
      true,
      {
        ignore: ["custom-elements"],
      },
    ],
    "at-rule-no-unknown": [
      true,
      {
        ignoreAtRules: [
          "tailwind",
          "apply",
          "variants",
          "responsive",
          "screen",
        ],
      },
    ],
    "custom-property-empty-line-before": null,
    "value-keyword-case": [
      "lower",
      {
        ignoreProperties: ["font-family"],
      },
    ],
    "property-no-vendor-prefix": null,
    "value-no-vendor-prefix": null,
    "length-zero-no-unit": true,
    "font-family-name-quotes": "always-where-recommended",
  },
  ignoreFiles: [
    "node_modules/**/*",
    "dist/**/*",
    "build/**/*",
    ".svelte-kit/**/*",
  ],
};
