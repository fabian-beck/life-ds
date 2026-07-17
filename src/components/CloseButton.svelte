<script>
  import { mdiClose } from "@mdi/js";

  export let ariaLabel;
  export let variant = "light"; // "dark" | "light" | "theme"
  export let size = "medium"; // "small" | "medium" | "large" | "responsive"
  export let position = "inline"; // "inline" | "absolute"

  let className = "";
  export { className as class };
</script>

<button
  type="button"
  class="close-button variant-{variant} size-{size} position-{position} {className}"
  on:click
  aria-label={ariaLabel}
>
  <svg class="icon" viewBox="0 0 24 24" role="presentation" aria-hidden="true">
    <path d={mdiClose} />
  </svg>
</button>

<style>
  .close-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.4rem;
    border-radius: 999px;
    cursor: pointer;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      transform 0.2s ease;
    font-family: inherit;
    font-weight: 500;
    line-height: 1;
  }

  .close-button:hover,
  .close-button:focus-visible {
    outline: none;
  }

  .close-button:active {
    transform: scale(0.95);
  }

  /* Position variants */
  .position-inline {
    position: relative;
  }

  .position-absolute {
    position: absolute;
    top: 1rem;
    right: 1rem;
  }

  /* Size variants */
  .size-small {
    width: 2rem;
    height: 2rem;
    padding: 0.4rem;
  }

  .size-small .icon {
    width: 1.2rem;
    height: 1.2rem;
  }

  .size-medium {
    width: 2.5rem;
    height: 2.5rem;
    padding: 0.5rem;
  }

  .size-medium .icon {
    width: 1.5rem;
    height: 1.5rem;
  }

  .size-large {
    width: 2.75rem;
    height: 2.75rem;
    padding: 0.625rem;
  }

  .size-large .icon {
    width: 1.5rem;
    height: 1.5rem;
  }

  .size-responsive {
    padding: clamp(0.3rem, 0.9vh, 0.45rem) clamp(0.7rem, 2.2vw, 0.95rem);
    font-size: clamp(0.75rem, 1.2vh, 0.85rem);
  }

  .size-responsive .icon {
    width: clamp(0.9rem, 1.5vh, 1.2rem);
    height: clamp(0.9rem, 1.5vh, 1.2rem);
    flex-shrink: 0;
  }

  /* Variant: dark - for dark overlays (ImageViewer, NetworkModal) */
  .variant-dark {
    border: 1px solid rgba(255, 255, 255, 0.3);
    background-color: rgba(0, 0, 0, 0.6);
    color: #ffffff;
  }

  .variant-dark:hover,
  .variant-dark:focus-visible {
    background-color: rgba(0, 0, 0, 0.8);
    border-color: rgba(255, 255, 255, 0.5);
    transform: scale(1.05);
  }

  /* Variant: light - for light overlays (AIDisclaimerModal, StoryView) */
  .variant-light {
    border: 1px solid rgba(148, 163, 184, 0.3);
    background-color: rgba(255, 255, 255, 0.05);
    color: #e2e8f0;
  }

  .variant-light:hover,
  .variant-light:focus-visible {
    background-color: rgba(255, 255, 255, 0.1);
    border-color: rgba(148, 163, 184, 0.5);
  }

  /* Variant: theme - theme-aware using CSS custom properties */
  .variant-theme {
    border: 1px solid var(--story-primary, rgba(148, 163, 184, 0.3));
    background-color: rgba(255, 255, 255, 0.05);
    color: var(--story-primary, #e2e8f0);
  }

  .variant-theme:hover,
  .variant-theme:focus-visible {
    background-color: rgba(255, 255, 255, 0.1);
    border-color: var(--story-primary, rgba(148, 163, 184, 0.5));
  }

  /* Mobile responsive adjustments for size-responsive */
  @media (max-height: 450px) and (orientation: landscape) {
    .size-responsive {
      padding: 0.2rem 0.4rem;
      font-size: 0.6rem;
    }

    .size-responsive .icon {
      width: 0.75rem;
      height: 0.75rem;
    }
  }

  @media (max-width: 767px) {
    .size-large {
      width: 2.5rem;
      height: 2.5rem;
      padding: 0.5rem;
    }

    .size-large .icon {
      width: 1.4rem;
      height: 1.4rem;
    }
  }

  .icon {
    fill: currentColor;
    flex-shrink: 0;
  }
</style>
