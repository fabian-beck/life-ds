<script>
  import { tick, onDestroy } from "svelte";
  import { mdiAccountMultipleOutline } from "@mdi/js";
  import { _ } from "../stores/language";
  import { displayName } from "../utils/helpers.js";
  import {
    relationshipRoleLabel,
    relationshipMetaValueLabel,
  } from "../utils/relationshipLabels.js";

  export let person = {};
  export let personKey = "";
  export let visiblePersonInfo = null;
  export let onToggle = () => {};
  export let onOpenNetwork = null; // Optional: callback to open the full network view
  export let containerSelector = null; // Optional: restrict positioning to container (e.g., ".modal-content")
  export let subcategory = null; // Optional: subcategory to display instead of full relationship_type
  export let styleConfig = null; // Optional: story style whose colors and font the tooltip inherits
  export let stacked = false; // Optional: vertical layout with role label below name
  export let showRole = true; // Optional: hide the role line (e.g. when a surrounding box label already names it)

  let buttonElement;
  let tooltipElement;
  let tooltipContent;
  let scrollContainer;

  onDestroy(() => {
    // Clean up tooltip from body when component is destroyed
    if (tooltipElement && tooltipElement.parentNode) {
      tooltipElement.parentNode.removeChild(tooltipElement);
      tooltipElement = null;
    }
    // Remove scroll listener
    if (scrollContainer) {
      scrollContainer.removeEventListener("scroll", handleScroll);
    }
  });

  function handleScroll() {
    // Close tooltip when scrolling
    if (isExpanded && tooltipElement) {
      onToggle(personKey);
    }
  }

  function truncateName(name) {
    if (!name) return "";

    // Remove text in brackets (parentheses or square brackets)
    let truncated = name.replace(/\s*[([].*?[)\]]/g, "");

    // Remove text after comma
    const commaIndex = truncated.indexOf(",");
    if (commaIndex !== -1) {
      truncated = truncated.substring(0, commaIndex);
    }

    return truncated.trim();
  }

  function handleClick(event) {
    const wasExpanded = isExpanded;
    onToggle(personKey, event);

    if (!wasExpanded) {
      // Tooltip is being opened, move to body and position it
      tick().then(() => {
        if (tooltipContent) {
          // Move tooltip to body to escape backdrop-filter containment
          tooltipElement = tooltipContent;
          // Remove from current parent if it has one
          if (tooltipElement.parentNode) {
            tooltipElement.parentNode.removeChild(tooltipElement);
          }
          document.body.appendChild(tooltipElement);

          // Apply style config CSS variables to tooltip
          if (styleConfig) {
            if (styleConfig.primary) {
              tooltipElement.style.setProperty(
                "--story-primary",
                styleConfig.primary
              );
            }
            if (styleConfig.secondary) {
              tooltipElement.style.setProperty(
                "--story-secondary",
                styleConfig.secondary
              );
            }
            if (styleConfig.bodyFont) {
              tooltipElement.style.setProperty(
                "--story-body-font",
                `"${styleConfig.bodyFont}", Inter, sans-serif`
              );
            }
          }

          positionTooltip();

          // Attach scroll listener to container
          if (containerSelector && !scrollContainer) {
            scrollContainer = document.querySelector(containerSelector);
            if (scrollContainer) {
              scrollContainer.addEventListener("scroll", handleScroll);
            }
          }
        }
      });
    } else if (tooltipElement) {
      // Tooltip is being closed, remove from body
      if (tooltipElement.parentNode) {
        tooltipElement.parentNode.removeChild(tooltipElement);
      }
      tooltipElement = null;

      // Remove scroll listener
      if (scrollContainer) {
        scrollContainer.removeEventListener("scroll", handleScroll);
        scrollContainer = null;
      }
    }
  }

  function positionTooltip() {
    if (!buttonElement || !tooltipElement) return;

    const buttonRect = buttonElement.getBoundingClientRect();
    const tooltipRect = tooltipElement.getBoundingClientRect();
    const padding = 16;
    const offset = 8;

    // Get container bounds if containerSelector is provided
    let containerRect = null;
    if (containerSelector) {
      const container = document.querySelector(containerSelector);
      if (container) {
        containerRect = container.getBoundingClientRect();
      }
    }

    // Use container bounds if available, otherwise use viewport
    const boundaryTop = containerRect ? containerRect.top : 0;
    const boundaryBottom = containerRect
      ? containerRect.bottom
      : window.innerHeight;
    const boundaryLeft = containerRect ? containerRect.left : 0;
    const boundaryRight = containerRect
      ? containerRect.right
      : window.innerWidth;

    // Check if there's enough space above
    const spaceAbove = buttonRect.top - boundaryTop;
    const spaceBelow = boundaryBottom - buttonRect.bottom;
    const tooltipHeight = tooltipRect.height;

    // Position vertically - prefer top if there's enough space
    let topPos;
    if (spaceAbove >= tooltipHeight + offset + padding) {
      // Position above
      topPos = buttonRect.top - tooltipHeight - offset;
    } else if (spaceBelow >= tooltipHeight + offset + padding) {
      // Position below
      topPos = buttonRect.bottom + offset;
    } else {
      // Not enough space either way, prefer top but clamp to container
      topPos = Math.max(
        boundaryTop + padding,
        buttonRect.top - tooltipHeight - offset
      );
    }

    tooltipElement.style.top = `${topPos}px`;

    // Position horizontally - center on button by default
    let leftPos =
      buttonRect.left + buttonRect.width / 2 - tooltipRect.width / 2;

    // Clamp horizontal position to container boundaries
    const minLeft = boundaryLeft + padding;
    const maxLeft = boundaryRight - tooltipRect.width - padding;
    leftPos = Math.max(minLeft, Math.min(leftPos, maxLeft));

    tooltipElement.style.left = `${leftPos}px`;
  }

  $: isExpanded = visiblePersonInfo === personKey;
  $: truncatedName = truncateName(person.person_name);
  $: isLongName = truncatedName.length > 15;
  // Only the collective kinds get a label; a person is the default and
  // needs no announcement.
  $: entityLabel =
    person.entity_kind === "organization" || person.entity_kind === "group"
      ? $_(`network.entity.${person.entity_kind}`)
      : null;
</script>

<div class="person-info-wrapper">
  <button
    type="button"
    class="person-chip {person.strength ? `strength-${person.strength}` : ''}"
    class:stacked
    bind:this={buttonElement}
    on:click|stopPropagation={handleClick}
    aria-label={$_("person.show_info", { name: person.person_name })}
    aria-expanded={isExpanded}
  >
    <span class="person-name" class:long-name={isLongName}>{truncatedName}</span
    >
    {#if showRole}
      <!-- `relationship_type` is a machine token the datasets keep in every
           language, so it is resolved through the locale rather than printed. -->
      <span class="person-role"
        >{relationshipRoleLabel(
          $_,
          subcategory ?? person.relationship_type
        )}</span
      >
    {/if}
  </button>
</div>

{#if isExpanded}
  <div class="person-info-tooltip" bind:this={tooltipContent}>
    <p class="tooltip-title">
      {person.person_name}
    </p>
    {#if entityLabel || person.qualifier}
      <!-- A connection typed as an organization or a group says so before
           its relationship metadata, and the qualifier carries the short
           descriptor that used to hide in a parenthetical of the name. The
           entity label is localized from the entity_kind token; the
           qualifier is data and arrives already in the reader's language. -->
      <p class="tooltip-entity">
        {[entityLabel, person.qualifier].filter(Boolean).join(" · ")}
      </p>
    {/if}
    <p class="tooltip-relationship">
      {person.relationship_description}
    </p>
    {#if person.strength}
      <!-- The value is a machine token ("strong") in every language, so it
           is resolved through the locale like the label next to it. A
           connection is a mutual tie, so its strength is all the metadata
           the tooltip shows: the datasets that still carry an interaction
           frequency, a direction of influence, years, or activity tags
           predate the schema (see data/outdated.md), and those fields are
           ignored. -->
      <div class="tooltip-meta">
        <span class="meta-item">
          <span class="meta-label">{$_("person.strength")}</span>
          <span class="meta-value strength-{person.strength}"
            >{relationshipMetaValueLabel($_, "strength", person.strength)}</span
          >
        </span>
      </div>
    {/if}
    {#if onOpenNetwork}
      <button
        type="button"
        class="tooltip-network-btn"
        on:click|stopPropagation={() => {
          onToggle(personKey);
          onOpenNetwork();
        }}
        aria-label={$_("story.show_network")}
      >
        <svg
          class="icon"
          viewBox="0 0 24 24"
          role="presentation"
          aria-hidden="true"
        >
          <path d={mdiAccountMultipleOutline} />
        </svg>
        <span>{$_("story.show_network")}</span>
      </button>
    {/if}
  </div>
{/if}

<style>
  .person-info-wrapper {
    position: relative;
  }

  .person-chip {
    appearance: none;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: rgba(15, 23, 42, 0.3);
    backdrop-filter: blur(8px);
    color: #e2e8f0;
    padding: 0.4rem 0.75rem;
    border-radius: 999px;
    font-size: 0.8rem;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    overflow: visible;
    height: 2rem;
    box-sizing: border-box;
    filter: drop-shadow(
      0 0 2px var(--story-secondary, rgba(56, 189, 248, 0.15))
    );
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      border-width 0.2s ease,
      transform 0.2s ease;
    pointer-events: auto;
  }

  /* Relationship strength border variations */
  .person-chip.strength-weak {
    border-width: 1px;
    border-style: dotted;
    border-color: rgba(148, 163, 184, 0.3);
    padding: 0.4rem 0.75rem;
  }

  .person-chip.strength-moderate {
    border-width: 1px;
    border-style: solid;
    border-color: rgba(148, 163, 184, 0.3);
    padding: 0.4rem 0.75rem;
  }

  .person-chip.strength-strong {
    border-width: 2.5px;
    border-style: solid;
    border-color: rgba(148, 163, 184, 0.6);
    padding: calc(0.4rem - 1.5px) calc(0.75rem - 1.5px);
  }

  .person-chip.stacked {
    flex-direction: column;
    justify-content: center;
    gap: 0.15rem;
    height: auto;
    min-height: 2.2rem;
    padding: 0.3rem 0.55rem;
    border-radius: 0.6rem;
    text-align: center;
  }

  .person-chip.stacked.strength-strong {
    padding: calc(0.3rem - 1.5px) calc(0.55rem - 1.5px);
  }

  .person-chip.stacked .person-role {
    justify-content: center;
    text-align: center;
  }

  .person-chip.stacked .person-name {
    max-width: 160px;
  }

  .person-chip:hover,
  .person-chip:focus {
    background: rgba(255, 255, 255, 0.12);
    border-color: var(--story-secondary, rgba(148, 163, 184, 0.5));
    transform: translateY(-1px);
    outline: none;
  }

  /* Compact person chips for landscape mobile */
  @media (max-height: 450px) {
    .person-chip {
      padding: 0.25rem 0.5rem;
      font-size: 0.65rem;
      gap: 0.35rem;
      background: rgba(15, 23, 42, 0.25);
      border-color: rgba(148, 163, 184, 0.2);
      height: 1.5rem;
    }

    .person-chip.strength-weak,
    .person-chip.strength-moderate {
      padding: 0.25rem 0.5rem;
    }

    .person-chip.strength-strong {
      padding: calc(0.25rem - 1.5px) calc(0.5rem - 1.5px);
    }

    .subcategory {
      font-size: 0.55rem;
      padding: 0.1rem 0.3rem;
    }
  }

  .person-chip.strength-weak:hover,
  .person-chip.strength-weak:focus {
    border-color: rgba(148, 163, 184, 0.45);
  }

  .person-chip.strength-moderate:hover,
  .person-chip.strength-moderate:focus {
    border-color: rgba(148, 163, 184, 0.5);
  }

  .person-chip.strength-strong:hover,
  .person-chip.strength-strong:focus {
    border-color: rgba(148, 163, 184, 0.8);
  }

  .person-chip[aria-expanded="true"] {
    background: rgba(255, 255, 255, 0.15);
    border-color: var(--story-secondary, rgba(148, 163, 184, 0.6));
  }

  .person-chip.strength-weak[aria-expanded="true"] {
    border-color: rgba(148, 163, 184, 0.5);
  }

  .person-chip.strength-moderate[aria-expanded="true"] {
    border-color: rgba(148, 163, 184, 0.6);
  }

  .person-chip.strength-strong[aria-expanded="true"] {
    border-color: rgba(148, 163, 184, 0.9);
  }

  /* line-height 1 clips descenders (g, y) under overflow: hidden, and a
     little side padding keeps glyph overhangs from being cut at the edges */
  .person-name {
    font-weight: 600;
    color: #e2e8f0;
    max-width: 150px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    line-height: 1.25;
    padding: 0 0.15em;
    font-family: var(--story-body-font, Inter, sans-serif);
  }

  .person-name.long-name {
    font-size: 0.72rem;
  }

  .person-role {
    font-weight: 400;
    color: var(--story-secondary, #94a3b8);
    font-size: 0.6rem;
    text-transform: uppercase;
    line-height: 1.2;
    overflow: visible;
    display: flex;
    align-items: center;
    font-family: var(--story-body-font, Inter, sans-serif);
  }

  .person-info-tooltip {
    position: fixed;
    min-width: 240px;
    max-width: min(300px, 90vw);
    background: rgba(15, 23, 42, 0.95);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 0.5rem;
    padding: 0.5rem 0.75rem;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
    z-index: 10000;
    animation: fadeInTooltip 0.2s ease;
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
    margin: 0 0 0.35rem 0;
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--story-primary, #f8fafc);
    font-family: var(--story-body-font, Inter, sans-serif);
  }

  .tooltip-entity {
    margin: -0.2rem 0 0.35rem 0;
    font-size: 0.68rem;
    color: var(--story-secondary, #94a3b8);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    font-family: var(--story-body-font, Inter, sans-serif);
  }

  .tooltip-relationship {
    margin: 0 0 0.3rem 0;
    font-size: 0.78rem;
    color: #e2e8f0;
    line-height: 1.4;
    font-family: var(--story-body-font, Inter, sans-serif);
  }

  .tooltip-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.35rem;
    padding-top: 0.35rem;
    border-top: 1px solid rgba(148, 163, 184, 0.2);
  }

  .meta-item {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.65rem;
  }

  .meta-label {
    color: rgba(148, 163, 184, 0.8);
    font-weight: 500;
    font-family: var(--story-body-font, Inter, sans-serif);
  }

  .meta-value {
    font-weight: 600;
    text-transform: capitalize;
    color: rgba(226, 232, 240, 0.9);
    font-family: var(--story-body-font, Inter, sans-serif);
  }

  .meta-value.strength-strong {
    font-weight: 800;
    color: rgba(226, 232, 240, 1);
    text-transform: uppercase;
    letter-spacing: 0.025em;
  }

  .meta-value.strength-moderate {
    font-weight: 600;
    color: rgba(226, 232, 240, 0.9);
  }

  .meta-value.strength-weak {
    font-weight: 400;
    color: rgba(226, 232, 240, 0.7);
    font-style: italic;
  }

  .tooltip-network-btn {
    appearance: none;
    width: 100%;
    margin-top: 0.5rem;
    padding: 0.35rem 0.5rem;
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 0.3rem;
    background: rgba(255, 255, 255, 0.05);
    color: var(--story-secondary, #94a3b8);
    font-size: 0.7rem;
    font-weight: 500;
    font-family: var(--story-body-font, Inter, sans-serif);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.4rem;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      color 0.2s ease;
  }

  .tooltip-network-btn:hover,
  .tooltip-network-btn:focus {
    background: rgba(255, 255, 255, 0.1);
    border-color: var(--story-secondary, rgba(148, 163, 184, 0.5));
    color: var(--story-primary, #e2e8f0);
    outline: none;
  }

  .tooltip-network-btn .icon {
    width: 0.85rem;
    height: 0.85rem;
    fill: currentColor;
  }
</style>
