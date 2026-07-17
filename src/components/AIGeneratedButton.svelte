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

  /* Small variant - compact hanging tag (StoryView) */
  .ai-generated-button.small {
    gap: 0.25rem;
    padding: 0.2rem 0.4rem;
    margin: 0;
    border-radius: 0 0 0.25rem 0.25rem;
    background: rgba(15, 23, 42, 0.5);
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-top: none;
    color: #fbbf24;
    font-size: 0.6rem;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
    backdrop-filter: blur(12px);
  }

  .ai-generated-button.small svg {
    width: 10px;
    height: 10px;
  }

  .ai-generated-button.small:hover {
    background: rgba(15, 23, 42, 0.65);
    border-color: rgba(251, 191, 36, 0.3);
  }
</style>
