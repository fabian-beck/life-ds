<script>
  import { mdiClose, mdiAccountMultipleOutline } from "@mdi/js";
  import PersonChip from "./PersonChip.svelte";

  export let egoNetwork = null;
  export let personName = "";
  export let styleConfig = null;
  export let onClose = () => {};

  function storyStyleVars(style) {
    if (!style || typeof style !== "object") return "";
    const segments = [];
    if (style.background) segments.push(`--story-bg: ${style.background}`);
    if (style.backgroundRgb)
      segments.push(`--story-bg-rgb: ${style.backgroundRgb}`);
    if (style.primary) segments.push(`--story-primary: ${style.primary}`);
    if (style.secondary) segments.push(`--story-secondary: ${style.secondary}`);
    if (style.backgroundPatternDataUrl) {
      segments.push(
        `--story-pattern-image: url(${style.backgroundPatternDataUrl})`
      );
    }
    if (style.headingFont) {
      segments.push(
        `--story-heading-font: "${style.headingFont}", Inter, sans-serif`
      );
    }
    if (style.bodyFont) {
      segments.push(
        `--story-body-font: "${style.bodyFont}", Inter, sans-serif`
      );
    }
    return segments.join("; ");
  }

  let visiblePersonInfo = null;

  function groupPeopleByType(connections) {
    const groups = {};
    connections.forEach((connection) => {
      const type = connection.relationship_type || "other";
      if (!groups[type]) {
        groups[type] = [];
      }
      groups[type].push(connection);
    });
    return groups;
  }

  function togglePersonInfo(personKey) {
    if (visiblePersonInfo === personKey) {
      visiblePersonInfo = null;
    } else {
      visiblePersonInfo = personKey;
    }
  }

  function handleClickOutside(event) {
    const personWrapper = event.target.closest(".person-info-wrapper");
    if (!personWrapper && visiblePersonInfo !== null) {
      visiblePersonInfo = null;
    }
  }

  $: connections = egoNetwork?.connections || [];
  $: groupedPeople = groupPeopleByType(connections);
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="modal-overlay" on:click={onClose}>
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="network-modal" style={storyStyleVars(styleConfig)} on:click|stopPropagation>
    <div class="modal-header">
      <h3 class="modal-title">
        <svg
          class="icon"
          viewBox="0 0 24 24"
          role="presentation"
          aria-hidden="true"
        >
          <path d={mdiAccountMultipleOutline} />
        </svg>
        {personName}'s Network
      </h3>
      <button
        type="button"
        class="modal-close"
        on:click={onClose}
        aria-label="Close modal"
      >
        <svg
          class="icon"
          viewBox="0 0 24 24"
          role="presentation"
          aria-hidden="true"
        >
          <path d={mdiClose} />
        </svg>
      </button>
    </div>
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div class="modal-content" on:click={handleClickOutside}>
      {#if egoNetwork?.network_summary}
        <div class="network-summary">
          <p class="summary-text">{egoNetwork.network_summary}</p>
        </div>
      {/if}
      {#each Object.entries(groupedPeople).sort( ([a], [b]) => {
        if (a === 'family') return -1;
        if (b === 'family') return 1;
        return a.localeCompare(b);
      } ) as [type, people]}
        <div class="person-group">
          <h4 class="group-title">
            {type}
            <span class="group-count">({people.length})</span>
          </h4>
          <div class="group-people">
            {#each people as person, idx}
              {@const personKey = `${type}-${idx}`}
              <PersonChip
                {person}
                {personKey}
                {visiblePersonInfo}
                onToggle={togglePersonInfo}
                containerSelector=".modal-content"
              />
            {/each}
          </div>
        </div>
      {/each}
    </div>
  </div>
</div>

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.95);
    backdrop-filter: blur(8px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: fadeIn 0.2s ease;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  .network-modal {
    background: linear-gradient(
        180deg,
        rgba(255, 255, 255, 0.03) 0%,
        rgba(0, 0, 0, 0.28) 100%
      ),
      rgba(var(--story-bg-rgb, 15, 23, 42), 0.95);
    backdrop-filter: blur(12px);
    width: 100%;
    height: 100%;
    max-width: 100vw;
    max-height: 100vh;
    display: flex;
    flex-direction: column;
    animation: slideUp 0.3s ease;
    position: relative;
    overflow: hidden;
    isolation: isolate;
  }

  .network-modal::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background-image: var(--story-pattern-image, none);
    background-size: 200px 200px;
    background-repeat: repeat;
    opacity: 0.35;
    mix-blend-mode: overlay;
    z-index: 0;
  }

  .network-modal > * {
    position: relative;
    z-index: 1;
  }

  @keyframes slideUp {
    from {
      opacity: 0;
      transform: translateY(2rem);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .modal-header {
    padding: 1.5rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .modal-title {
    margin: 0;
    font-size: 1.35rem;
    font-weight: 600;
    color: var(--story-primary, #f8fafc);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-family: var(--story-heading-font, Inter, sans-serif);
  }

  .modal-title .icon {
    color: var(--story-secondary, #38bdf8);
  }

  .icon {
    width: 1.5rem;
    height: 1.5rem;
    fill: currentColor;
    flex: 0 0 auto;
  }

  .modal-close {
    appearance: none;
    width: 3rem;
    height: 3rem;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.3);
    background: rgba(0, 0, 0, 0.6);
    color: #ffffff;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      transform 0.2s ease;
  }

  .modal-close:hover,
  .modal-close:focus {
    background: rgba(0, 0, 0, 0.8);
    border-color: rgba(255, 255, 255, 0.6);
    transform: scale(1.05);
    outline: none;
  }

  .modal-content {
    padding: 1.5rem;
    overflow-y: auto;
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }

  .network-summary {
    padding: 0;
  }

  .summary-text {
    margin: 0;
    font-size: 0.95rem;
    line-height: 1.6;
    color: #e2e8f0;
    font-family: var(--story-body-font, Inter, sans-serif);
  }

  .person-group {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .group-title {
    margin: 0;
    font-size: 0.9rem;
    text-transform: capitalize;
    color: var(--story-primary, #f8fafc);
    font-weight: 600;
    font-family: var(--story-heading-font, Inter, sans-serif);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    letter-spacing: 0.01em;
  }

  .group-count {
    font-size: 0.75rem;
    color: var(--story-secondary, #38bdf8);
    font-weight: 600;
  }

  .group-people {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  @media (min-width: 768px) {
    .modal-content {
      padding: 2rem;
    }

    .modal-header {
      padding: 2rem;
    }
  }
</style>
