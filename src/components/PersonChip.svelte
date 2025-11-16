<script>
  import { tick } from "svelte";

  export let person = {};
  export let personKey = "";
  export let visiblePersonInfo = null;
  export let onToggle = () => {};
  export let containerSelector = null; // Optional: restrict positioning to container (e.g., ".modal-content")

  let buttonElement;
  let tooltipElement;

  function handleClick(event) {
    const wasExpanded = isExpanded;
    onToggle(personKey, event);

    if (!wasExpanded) {
      // Tooltip is being opened, position it
      tick().then(() => {
        positionTooltip();
      });
    }
  }

  function positionTooltip() {
    if (!buttonElement || !tooltipElement) return;

    const buttonRect = buttonElement.getBoundingClientRect();
    const tooltipRect = tooltipElement.getBoundingClientRect();
    const padding = 16;

    let boundaryRect;
    if (containerSelector) {
      const container = document.querySelector(containerSelector);
      boundaryRect = container?.getBoundingClientRect();
    }

    if (!boundaryRect) {
      // Use viewport as boundary
      boundaryRect = {
        left: 0,
        right: window.innerWidth,
        width: window.innerWidth,
      };
    }

    // Check if tooltip would overflow on the right
    const wouldOverflowRight =
      buttonRect.left + tooltipRect.width > boundaryRect.right - padding;

    // Check if tooltip would overflow on the left
    const wouldOverflowLeft = buttonRect.left - boundaryRect.left < padding;

    if (wouldOverflowRight && !wouldOverflowLeft) {
      // Align to right edge of button
      tooltipElement.style.left = "auto";
      tooltipElement.style.right = "0";
      tooltipElement.style.transform = "none";
    } else if (wouldOverflowLeft) {
      // Align to left edge of button
      tooltipElement.style.left = "0";
      tooltipElement.style.right = "auto";
      tooltipElement.style.transform = "none";
    } else {
      // Default position (left-aligned)
      tooltipElement.style.left = "0";
      tooltipElement.style.right = "auto";
      tooltipElement.style.transform = "none";
    }
  }

  $: isExpanded = visiblePersonInfo === personKey;
</script>

<div class="person-info-wrapper">
  <button
    type="button"
    class="person-chip"
    bind:this={buttonElement}
    on:click|stopPropagation={handleClick}
    aria-label={`Show information about ${person.person_name}`}
    aria-expanded={isExpanded}
  >
    <span class="person-name">{person.person_name}</span>
    <span class="person-role">{person.relationship_type}</span>
  </button>
  {#if isExpanded}
    <div class="person-info-tooltip" bind:this={tooltipElement}>
      <p class="tooltip-title">
        {person.person_name}
      </p>
      <p class="tooltip-relationship">
        {person.relationship_description}
      </p>
      {#if person.start_year || person.end_year}
        <p class="tooltip-years">
          {#if person.start_year && person.end_year}
            {person.start_year}–{person.end_year}
          {:else if person.start_year}
            From {person.start_year}
          {:else if person.end_year}
            Until {person.end_year}
          {/if}
        </p>
      {/if}
      {#if person.shared_activities?.length}
        <p class="tooltip-activities">
          {person.shared_activities.join(", ")}
        </p>
      {/if}
      {#if person.strength || person.interaction_frequency || person.influence_direction}
        <div class="tooltip-meta">
          {#if person.strength}
            <span class="meta-item">
              <span class="meta-label">Strength:</span>
              <span class="meta-value strength-{person.strength}"
                >{person.strength}</span
              >
            </span>
          {/if}
          {#if person.interaction_frequency}
            <span class="meta-item">
              <span class="meta-label">Frequency:</span>
              <span class="meta-value">{person.interaction_frequency}</span>
            </span>
          {/if}
          {#if person.influence_direction}
            <span class="meta-item">
              <span class="meta-label">Influence:</span>
              <span class="meta-value"
                >{person.influence_direction.replace(/_/g, " ")}</span
              >
            </span>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .person-info-wrapper {
    position: relative;
  }

  .person-chip {
    appearance: none;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: rgba(255, 255, 255, 0.05);
    color: #e2e8f0;
    padding: 0.4rem 0.75rem;
    border-radius: 999px;
    font-size: 0.8rem;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      transform 0.2s ease;
  }

  .person-chip:hover,
  .person-chip:focus {
    background: rgba(255, 255, 255, 0.12);
    border-color: var(--story-secondary, rgba(148, 163, 184, 0.5));
    transform: translateY(-1px);
    outline: none;
  }

  .person-chip[aria-expanded="true"] {
    background: rgba(255, 255, 255, 0.15);
    border-color: var(--story-secondary, rgba(148, 163, 184, 0.6));
  }

  .person-name {
    font-weight: 600;
    color: #e2e8f0;
  }

  .person-role {
    font-weight: 400;
    color: var(--story-secondary, #94a3b8);
    font-size: 0.75rem;
    text-transform: capitalize;
  }

  .person-info-tooltip {
    position: absolute;
    top: calc(100% + 0.5rem);
    left: 0;
    min-width: 280px;
    max-width: min(340px, 90vw);
    background: rgba(15, 23, 42, 0.95);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
    z-index: 10;
    animation: fadeInTooltip 0.2s ease;
    transition:
      left 0.2s ease,
      right 0.2s ease,
      transform 0.2s ease;
  }

  @keyframes fadeInTooltip {
    from {
      opacity: 0;
      transform: translateY(-0.5rem);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .tooltip-title {
    margin: 0 0 0.5rem 0;
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--story-primary, #f8fafc);
  }

  .tooltip-relationship {
    margin: 0 0 0.5rem 0;
    font-size: 0.85rem;
    color: #e2e8f0;
    line-height: 1.5;
  }

  .tooltip-years {
    margin: 0 0 0.5rem 0;
    font-size: 0.75rem;
    color: var(--story-secondary, #94a3b8);
    font-weight: 500;
  }

  .tooltip-activities {
    margin: 0 0 0.5rem 0;
    font-size: 0.75rem;
    color: rgba(148, 163, 184, 0.85);
    font-style: italic;
    line-height: 1.4;
  }

  .tooltip-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid rgba(148, 163, 184, 0.2);
  }

  .meta-item {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.7rem;
  }

  .meta-label {
    color: rgba(148, 163, 184, 0.8);
    font-weight: 500;
  }

  .meta-value {
    font-weight: 600;
    text-transform: capitalize;
    color: rgba(226, 232, 240, 0.9);
  }

  .meta-value.strength-strong {
    color: #10b981;
  }

  .meta-value.strength-moderate {
    color: #f59e0b;
  }

  .meta-value.strength-weak {
    color: #94a3b8;
  }
</style>
