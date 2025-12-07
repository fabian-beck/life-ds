<script>
  import { mdiMagnifyPlusOutline, mdiAccountMultipleOutline } from "@mdi/js";
  import { _ } from "../stores/language";
  import { getThumbnailUrl } from "../utils/storyHelpers.js";

  export let person = {};
  export let portrait = null;
  export let personName = "";
  export let yearsLabel = "";
  export let rolesLabel = "";
  export let personSummary = "";
  export let egoNetwork = null;
  export let descriptionOverflows = new Set();
  export let onEnlargeImage = () => {};
  export let onOpenNetwork = () => {};
  export let checkOverflow = () => {};

  $: hasPersonSummary = Boolean(personSummary);

  function handleImageLoad(event) {
    const img = event.target;
    if (!img || !img.naturalWidth || !img.naturalHeight) return;

    const aspectRatio = img.naturalWidth / img.naturalHeight;
    let horizontalRadius, verticalRadius;

    if (aspectRatio > 1) {
      horizontalRadius = Math.min(92, 80 + (aspectRatio - 1) * 8);
      verticalRadius = 85;
    } else {
      horizontalRadius = 85;
      verticalRadius = Math.min(95, 88 + (1 / aspectRatio - 1) * 5);
    }

    const maskImage = `
      linear-gradient(to right, transparent 0%, black ${100 - horizontalRadius}%, black ${horizontalRadius}%, transparent 100%),
      linear-gradient(to bottom, transparent 0%, black ${100 - verticalRadius}%, black ${verticalRadius}%, transparent 100%),
      radial-gradient(at top left, transparent 0%, transparent 8%, black 12%),
      radial-gradient(at top right, transparent 0%, transparent 8%, black 12%),
      radial-gradient(at bottom left, transparent 0%, transparent 8%, black 12%),
      radial-gradient(at bottom right, transparent 0%, transparent 8%, black 12%)
    `;

    const maskComposite = "intersect";

    img.style.maskImage = maskImage;
    img.style.webkitMaskImage = maskImage;
    img.style.maskComposite = maskComposite;
    img.style.webkitMaskComposite = maskComposite;
  }
</script>

<div class="content overview-content">
  {#if portrait?.image}
    <figure class="overview-portrait">
      <button
        type="button"
        class="portrait-button"
        on:click={() =>
          onEnlargeImage({
            url: portrait.image,
            caption: portrait.caption || null,
            source: portrait.source || null,
            creator: portrait.creator || null,
            license: portrait.license || null,
            licenseUrl: portrait.licenseUrl || null,
          })}
        aria-label={$_("story.enlarge_portrait")}
      >
        <img
          src={getThumbnailUrl(portrait.image, 400)}
          srcset={`${getThumbnailUrl(portrait.image, 400)} 1x, ${getThumbnailUrl(portrait.image, 800)} 2x`}
          alt={portrait.alt ?? `Portrait of ${personName}`}
          loading="lazy"
          decoding="async"
          on:load={handleImageLoad}
        />
        <span class="enlarge-icon portrait-enlarge">
          <svg
            class="icon"
            viewBox="0 0 24 24"
            role="presentation"
            aria-hidden="true"
          >
            <path d={mdiMagnifyPlusOutline} />
          </svg>
        </span>
      </button>
    </figure>
  {/if}
  <div class="overview-text">
    <h2>{personName}</h2>
    {#if yearsLabel}
      <p class="overview-years">{yearsLabel}</p>
    {/if}
    {#if rolesLabel}
      <p class="overview-roles">{@html rolesLabel}</p>
    {/if}
    {#if egoNetwork?.connections && egoNetwork.connections.length > 0}
      <button
        type="button"
        class="overview-network-btn"
        on:click={onOpenNetwork}
        aria-label={$_("story.show_network")}
      >
        <svg
          class="icon icon-inline"
          viewBox="0 0 24 24"
          role="presentation"
          aria-hidden="true"
        >
          <path d={mdiAccountMultipleOutline} />
        </svg>
        <span class="network-btn-text">
          {egoNetwork.connections.length}
          {egoNetwork.connections.length === 1 ? "connection" : "connections"}
        </span>
      </button>
    {/if}
    {#if hasPersonSummary}
      <p
        class="description"
        class:has-fade={descriptionOverflows.has("overview")}
        use:checkOverflow={"overview"}
      >
        {personSummary}
      </p>
    {:else if person}
      <p class="description placeholder">
        {$_("story.no_summary")}
      </p>
    {/if}
  </div>
</div>

<style>
  .overview-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    text-align: center;
    max-width: 56rem;
    align-self: center;
    width: min(54rem, 100%);
    margin: 0 auto;
    position: relative;
    z-index: 4;
  }

  .overview-portrait {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    align-items: center;
    width: fit-content;
  }

  .overview-portrait img {
    max-width: 100%;
    max-height: min(25dvh, 180px);
    width: auto;
    height: auto;
    object-fit: contain;
    border-radius: 1rem;
    box-shadow: none;
    border: none;
    filter: saturate(0.55) contrast(0.8) brightness(0.92);
    mask-image: radial-gradient(
      ellipse 45% 55% at center,
      rgba(0, 0, 0, 1) 35%,
      rgba(0, 0, 0, 0.95) 50%,
      rgba(0, 0, 0, 0.7) 65%,
      rgba(0, 0, 0, 0.35) 78%,
      rgba(0, 0, 0, 0) 90%
    );
    -webkit-mask-image: radial-gradient(
      ellipse 45% 55% at center,
      rgba(0, 0, 0, 1) 35%,
      rgba(0, 0, 0, 0.95) 50%,
      rgba(0, 0, 0, 0.7) 65%,
      rgba(0, 0, 0, 0.35) 78%,
      rgba(0, 0, 0, 0) 90%
    );
  }

  .portrait-button {
    appearance: none;
    border: none;
    padding: 0;
    margin: 0;
    cursor: pointer;
    display: block;
    position: relative;
    background: transparent;
  }

  .portrait-button:focus {
    outline: none;
  }

  .overview-text {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .overview-text h2 {
    font-size: 1.5rem;
    line-height: 1.1;
    margin: 0;
    font-family: var(--story-heading-font, Inter, sans-serif);
    color: var(--story-primary, #f8fafc);
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .overview-years {
    font-size: 0.9rem;
    color: rgba(148, 163, 184, 0.95);
    font-weight: 500;
    margin: 0;
  }

  .overview-roles {
    font-size: 0.75rem;
    color: var(--story-secondary, #38bdf8);
    font-weight: 500;
    margin: 0;
    text-transform: uppercase;
  }

  .overview-text .description {
    margin-top: 0.35rem;
    font-size: 0.9rem;
    line-height: 1.5;
    margin-left: auto;
    margin-right: auto;
    font-family: var(--story-body-font, Inter, sans-serif);
    max-height: 30vh;
    overflow-y: auto;
    color: #e2e8f0;
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .overview-text .description.has-fade {
    padding-bottom: 5em;
    padding-right: 0.5em;
    -webkit-mask-image: linear-gradient(
      to bottom,
      black calc(100% - 5em),
      transparent 100%
    );
    mask-image: linear-gradient(
      to bottom,
      black calc(100% - 5em),
      transparent 100%
    );
  }

  .overview-text .description.placeholder {
    color: #94a3b8;
    font-style: italic;
  }

  .overview-network-btn {
    appearance: none;
    position: absolute;
    top: 1rem;
    right: 2vw;
    margin: 0;
    border: 1px solid var(--story-primary, rgba(148, 163, 184, 0.3));
    background: rgba(255, 255, 255, 0.05);
    color: var(--story-primary, #e2e8f0);
    padding: 0.5rem;
    border-radius: 50%;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.4rem;
    width: 2.5rem;
    height: 2.5rem;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      transform 0.2s ease;
    z-index: 10;
  }

  .overview-network-btn .icon {
    width: 1.25rem;
    height: 1.25rem;
    fill: currentColor;
  }

  .network-btn-text {
    display: none;
  }

  .overview-network-btn:hover,
  .overview-network-btn:focus {
    background: rgba(255, 255, 255, 0.12);
    border-color: var(--story-primary, rgba(148, 163, 184, 0.6));
    transform: scale(1.05);
    outline: none;
  }

  .overview-network-btn:active {
    transform: scale(0.98);
  }

  .icon {
    width: 1.1em;
    height: 1.1em;
    fill: currentColor;
    flex: 0 0 auto;
  }

  .icon-inline {
    width: 1em;
    height: 1em;
  }

  .enlarge-icon {
    position: absolute;
    bottom: 0.25rem;
    right: 0;
    width: 1.5rem;
    height: 1.5rem;
    background: rgba(15, 23, 42, 0.8);
    border-radius: 0.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    opacity: 1;
    transition: opacity 0.2s ease;
  }

  .enlarge-icon .icon {
    width: 1rem;
    height: 1rem;
    fill: var(--story-primary, #f8fafc);
  }

  /* Tablet and desktop styles */
  @media (min-width: 768px) and (min-height: 600px) {
    .portrait-enlarge {
      width: 2.5rem;
      height: 2.5rem;
      bottom: 0.75rem;
      right: 0;
    }

    .portrait-enlarge .icon {
      width: 1.5rem;
      height: 1.5rem;
    }

    .overview-portrait img {
      max-width: 340px;
    }

    .overview-content {
      flex-direction: row;
      align-items: center;
      flex-wrap: wrap;
      text-align: left;
      justify-content: center;
      gap: 3rem;
    }

    .overview-portrait {
      align-items: center;
    }

    .overview-portrait img {
      max-width: 420px;
      max-height: min(40dvh, 320px);
    }

    .overview-text {
      flex: 1;
      min-width: 300px;
      align-items: flex-start;
    }

    .overview-text h2 {
      font-size: 2.5rem;
    }

    .overview-years {
      font-size: 1.1rem;
    }

    .overview-roles {
      font-size: 1rem;
    }

    .overview-network-btn {
      position: static;
      margin-top: 0.75rem;
      padding: 0.4rem 0.85rem;
      border-radius: 999px;
      width: fit-content;
      height: auto;
      align-self: flex-start;
    }

    .overview-network-btn .icon {
      width: 1rem;
      height: 1rem;
    }

    .network-btn-text {
      display: inline;
    }

    .overview-text .description {
      font-size: 1.1rem;
      width: 100%;
      flex-basis: 100%;
      text-align: left;
      margin-top: 1rem;
      max-height: 45vh;
    }
  }
</style>
