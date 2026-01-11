<script>
  import { _ } from "../stores/language";

  /**
   * Variant of the button:
   * - "large": Larger button with border and background (for Landing page)
   * - "small": Smaller button without border, with text glow (for StoryView)
   */
  export let variant = "large";
  export let onClick = () => {};
</script>

<button
  class="ai-generated-button"
  class:large={variant === "large"}
  class:small={variant === "small"}
  on:click={onClick}
  aria-label={$_("landing.learn_about_ai")}
>
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width={variant === "large" ? 16 : 14}
    height={variant === "large" ? 16 : 14}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
  >
    <circle cx="12" cy="12" r="10"></circle>
    <line x1="12" y1="16" x2="12" y2="12"></line>
    <line x1="12" y1="8" x2="12.01" y2="8"></line>
  </svg>
  <span>{$_("landing.ai_generated_label")}</span>
</button>

<style>
  .ai-generated-button {
    display: inline-flex;
    align-items: center;
    cursor: pointer;
    transition: all 0.2s ease;
    font-weight: 500;
  }

  .ai-generated-button svg {
    flex-shrink: 0;
    opacity: 0.9;
  }

  .ai-generated-button.small svg {
    filter: drop-shadow(0 0 3px rgba(0, 0, 0, 1))
      drop-shadow(0 0 6px rgba(0, 0, 0, 0.8))
      drop-shadow(0 1px 2px rgba(0, 0, 0, 0.9));
  }

  /* Large variant - with border and background (Landing page) */
  .ai-generated-button.large {
    gap: 0.4rem;
    padding: 0.5rem 0.75rem;
    border-radius: 0.5rem;
    background: rgba(251, 191, 36, 0.12);
    border: 1px solid rgba(251, 191, 36, 0.3);
    color: #fbbf24;
    font-size: 0.8rem;
  }

  .ai-generated-button.large:hover {
    background: rgba(251, 191, 36, 0.18);
    border-color: rgba(251, 191, 36, 0.45);
  }

  /* Small variant - with border and background (StoryView) */
  .ai-generated-button.small {
    gap: 0.35rem;
    padding: 0.4rem 0.5rem;
    border-radius: 0.375rem;
    background: rgba(251, 191, 36, 0.12);
    border: 1px solid rgba(251, 191, 36, 0.3);
    color: #fbbf24;
    font-size: 0.7rem;
    text-shadow:
      0 0 8px rgba(0, 0, 0, 1),
      0 0 12px rgba(0, 0, 0, 0.8),
      0 1px 3px rgba(0, 0, 0, 0.9);
  }

  .ai-generated-button.small:hover {
    background: rgba(251, 191, 36, 0.18);
    border-color: rgba(251, 191, 36, 0.45);
  }
</style>
