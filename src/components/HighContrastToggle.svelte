<script>
  import { mdiContrastCircle } from "@mdi/js";
  import { highContrast, toggleHighContrast } from "../stores/contrast.js";
  import { _ } from "../stores/language";

  // Visual variant to match the neighbouring language selector.
  export let variant = "default"; // "default" | "sticky"
</script>

<button
  type="button"
  class="contrast-toggle {variant}"
  class:active={$highContrast}
  on:click={toggleHighContrast}
  aria-pressed={$highContrast}
  aria-label={$_("app.toggle_high_contrast")}
  title={$_("app.toggle_high_contrast")}
>
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path d={mdiContrastCircle} fill="currentColor" />
  </svg>
</button>

<style>
  .contrast-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.5rem;
    background: rgba(15, 23, 42, 0.9);
    border: 1px solid rgba(226, 232, 240, 0.2);
    border-radius: 0.375rem;
    color: #e2e8f0;
    cursor: pointer;
    backdrop-filter: blur(8px);
    transition: all 0.2s ease;
    line-height: 0;
  }

  .contrast-toggle svg {
    width: 1.25rem;
    height: 1.25rem;
    display: block;
  }

  .contrast-toggle:hover {
    background: rgba(15, 23, 42, 1);
    border-color: rgba(226, 232, 240, 0.4);
  }

  .contrast-toggle:focus-visible {
    outline: 2px solid #38bdf8;
    outline-offset: 2px;
  }

  .contrast-toggle.active {
    color: #38bdf8;
    border-color: rgba(56, 189, 248, 0.6);
  }

  .contrast-toggle.sticky {
    padding: 0.4rem;
    background: rgba(15, 23, 42, 0.6);
    border-color: rgba(148, 163, 184, 0.25);
  }

  .contrast-toggle.sticky svg {
    width: 1.05rem;
    height: 1.05rem;
  }
</style>
