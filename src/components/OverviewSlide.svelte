<script>
  import { mdiMagnifyPlusOutline } from "@mdi/js";
  import { _ } from "../stores/language";
  import { getThumbnailUrl } from "../utils/storyHelpers.js";
  import SeparatedList from "./SeparatedList.svelte";

  export let person = {};
  export let portrait = null;
  export let personName = "";
  export let yearsLabel = "";
  export let roles = [];
  export let styleConfig = null;
  export let personSummary = "";
  export let onEnlargeImage = () => {};

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
            url: portrait.full || portrait.image,
            caption: portrait.caption || null,
            source: portrait.source || null,
            creator: portrait.creator || null,
            license: portrait.license || null,
            licenseUrl: portrait.licenseUrl || null,
          })}
        aria-label={$_("story.enlarge_portrait")}
      >
        <img
          src={getThumbnailUrl(portrait, 400)}
          srcset={`${getThumbnailUrl(portrait, 400)} 1x, ${getThumbnailUrl(portrait, 800)} 2x`}
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
    {#if roles.length > 0}
      <p class="overview-roles">
        <SeparatedList items={roles} {styleConfig} />
      </p>
    {/if}
    {#if hasPersonSummary}
      <p class="description">
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
    max-height: min(40dvh, 300px);
    width: auto;
    height: auto;
    object-fit: contain;
    border-radius: 1rem;
    box-shadow: none;
    border: none;
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
    color: #e2e8f0;
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .overview-text .description.placeholder {
    color: #94a3b8;
    font-style: italic;
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
      max-width: 520px;
      max-height: min(50dvh, 450px);
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

    .overview-text .description {
      font-size: 1.1rem;
      width: 100%;
      flex-basis: 100%;
      text-align: left;
      margin-top: 1rem;
    }
  }
</style>
