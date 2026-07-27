<script>
  import { mdiContrastCircle } from "@mdi/js";
  import { onDestroy } from "svelte";
  import { highContrast, toggleHighContrast } from "../stores/contrast.js";
  import { _ } from "../stores/language";

  // Visual variant to match the neighbouring language selector.
  export let variant = "default"; // "default" | "sticky"

  let toastKey = "";
  let toastTimer;

  function handleToggle() {
    const enabled = !$highContrast;
    toggleHighContrast();
    toastKey = enabled
      ? "app.high_contrast_enabled"
      : "app.high_contrast_disabled";

    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastKey = "";
    }, 3000);
  }

  onDestroy(() => clearTimeout(toastTimer));
</script>

<button
  type="button"
  class="contrast-toggle {variant}"
  class:active={$highContrast}
  on:click={handleToggle}
  aria-pressed={$highContrast}
  aria-label={$_("app.toggle_high_contrast")}
  title={$_("app.toggle_high_contrast")}
>
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path d={mdiContrastCircle} fill="currentColor" />
  </svg>
</button>

{#if toastKey}
  <div
    class="contrast-toast"
    role="status"
    aria-live="polite"
    aria-atomic="true"
  >
    {$_(toastKey)}
  </div>
{/if}

<style>
  .contrast-toggle {
    /* Height is pinned to match the neighbouring language selector exactly
       (both use box-sizing: border-box); keep these values in sync with
       .language-selector in Landing.svelte. */
    height: 2.25rem;
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

  .contrast-toast {
    position: fixed;
    left: 50%;
    bottom: max(1.5rem, calc(env(safe-area-inset-bottom) + 1rem));
    z-index: 10000;
    max-width: min(28rem, calc(100vw - 2rem));
    transform: translateX(-50%);
    padding: 0.7rem 1rem;
    border: 1px solid rgba(226, 232, 240, 0.28);
    border-radius: 0.5rem;
    background: rgba(15, 23, 42, 0.96);
    box-shadow: 0 0.75rem 2rem rgba(0, 0, 0, 0.35);
    color: #f8fafc;
    font:
      500 0.9rem/1.35 system-ui,
      sans-serif;
    text-align: center;
    pointer-events: none;
    animation: toast-in 0.2s ease-out;
  }

  @keyframes toast-in {
    from {
      opacity: 0;
      transform: translate(-50%, 0.5rem);
    }
  }

  .contrast-toggle.sticky {
    height: 1.85rem;
    padding: 0.4rem;
    background: rgba(15, 23, 42, 0.6);
    border-color: rgba(148, 163, 184, 0.25);
  }

  .contrast-toggle.sticky svg {
    width: 1.05rem;
    height: 1.05rem;
  }

  /* Matches the .language-selector.sticky height bump at this breakpoint. */
  @media (min-width: 768px) {
    .contrast-toggle.sticky {
      height: 2rem;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .contrast-toast {
      animation: none;
    }
  }
</style>
