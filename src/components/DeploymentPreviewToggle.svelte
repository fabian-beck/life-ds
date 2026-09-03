<script>
  import { mdiEyeOffOutline, mdiEyeOutline } from "@mdi/js";
  import {
    previewDeployment,
    togglePreviewDeployment,
  } from "../stores/visibility.js";
  import { _ } from "../stores/language";

  // Development only: switch between the working view, which shows the
  // entries marked hidden in the registries, and the view the deployment
  // shows. Rendered next to the high-contrast toggle, in the same two sizes.
  const { variant = "default" } = $props(); // "default" | "sticky"

  const label = $derived(
    $previewDeployment
      ? $_("app.show_hidden_entries")
      : $_("app.preview_deployment")
  );
</script>

<button
  type="button"
  class="deployment-toggle {variant}"
  class:active={$previewDeployment}
  onclick={togglePreviewDeployment}
  aria-pressed={$previewDeployment}
  aria-label={label}
  title={label}
  data-deployment-preview
>
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path
      d={$previewDeployment ? mdiEyeOffOutline : mdiEyeOutline}
      fill="currentColor"
    />
  </svg>
</button>

<style>
  .deployment-toggle {
    /* Sized like the high-contrast toggle beside it; keep these values in
       sync with .contrast-toggle in HighContrastToggle.svelte. */
    height: 2.25rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.5rem;
    background: rgba(15, 23, 42, 0.9);
    border: 1px dashed rgba(251, 191, 36, 0.6);
    border-radius: 0.375rem;
    color: #fbbf24;
    cursor: pointer;
    backdrop-filter: blur(8px);
    transition: all 0.2s ease;
    line-height: 0;
  }

  .deployment-toggle svg {
    width: 1.25rem;
    height: 1.25rem;
    display: block;
  }

  .deployment-toggle:hover {
    background: rgba(15, 23, 42, 1);
    border-color: rgba(251, 191, 36, 0.9);
  }

  .deployment-toggle:focus-visible {
    outline: 2px solid #38bdf8;
    outline-offset: 2px;
  }

  .deployment-toggle.active {
    color: #e2e8f0;
    border-style: solid;
    border-color: rgba(226, 232, 240, 0.4);
  }

  .deployment-toggle.sticky {
    height: 1.85rem;
    padding: 0.4rem;
    background: rgba(15, 23, 42, 0.6);
  }

  .deployment-toggle.sticky svg {
    width: 1.05rem;
    height: 1.05rem;
  }

  @media (min-width: 768px) {
    .deployment-toggle.sticky {
      height: 2rem;
    }
  }
</style>
