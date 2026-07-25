<script>
  import { displayName, joinWithSeparator } from "../utils/helpers.js";
  import { computeYearsLabel, getThumbnailUrl } from "../utils/storyHelpers.js";

  export let person = null;
  export let personStyle = null;
  export let href = null;
  // Replaces the link's default navigation (the card handles the click itself).
  export let onClick = null;
  // Runs before `href` is followed, e.g. to remember scroll position. Unlike
  // `onClick` it leaves the normal link behaviour (and modifier-clicks) intact.
  export let onNavigate = null;
  // Localized accessible label; falls back to the person's name.
  export let ariaLabel = null;

  // Format lifespan for a person
  function formatLifespan(person) {
    if (!person) return "";
    return computeYearsLabel(person);
  }

  // Get initials from name for fallback
  function initialsFromName(name) {
    if (!name) return "?";
    return name
      .replace(/_/g, " ")
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((word) => word[0].toUpperCase())
      .join("");
  }

  $: lifespan = formatLifespan(person);
  $: roles = Array.isArray(person?.primaryRoles)
    ? joinWithSeparator(person.primaryRoles, personStyle)
    : "";

  function handleClick(e) {
    if (onNavigate) onNavigate(person);
    if (onClick) {
      e.preventDefault();
      onClick(person);
    }
  }
</script>

<a
  {href}
  class="person-card"
  style="--card-primary: {personStyle?.primary ||
    '#f8fafc'}; --card-secondary: {personStyle?.secondary ||
    '#38bdf8'}; --card-heading-font: {personStyle?.headingFont
    ? `'${personStyle.headingFont}', sans-serif`
    : 'inherit'}; --card-body-font: {personStyle?.bodyFont
    ? `'${personStyle.bodyFont}', sans-serif`
    : 'inherit'};"
  aria-label={ariaLabel || displayName(person?.name)}
  on:click={handleClick}
>
  {#if person?.portrait?.image}
    <figure class="person-thumb">
      <img
        src={getThumbnailUrl(person.portrait, 120)}
        srcset={`${getThumbnailUrl(person.portrait, 120)} 1x, ${getThumbnailUrl(person.portrait, 240)} 2x`}
        alt=""
        loading="lazy"
        decoding="async"
      />
    </figure>
  {:else}
    <figure class="person-thumb">
      <div class="thumb-fallback" aria-hidden="true">
        {initialsFromName(person?.name)}
      </div>
    </figure>
  {/if}
  <div class="card-info">
    <h4 class="card-name">{displayName(person?.name)}</h4>
    {#if lifespan}
      <p class="card-years">{lifespan}</p>
    {/if}
    {#if roles}
      <p class="card-roles">{@html roles}</p>
    {/if}
  </div>
</a>

<style>
  .person-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0;
    padding: 0.375rem 0.75rem 1rem;
    /* Surface tones are overridable so the card can sit on a story slide
       (default) or on the meta story's own dark page background. */
    background: var(--card-bg, rgba(15, 23, 42, 0.95));
    border-radius: 0.5rem;
    border: 1px solid var(--card-border, rgba(148, 163, 184, 0.2));
    text-decoration: none;
    color: inherit;
    transition:
      transform 0.2s ease,
      background 0.2s ease,
      border-color 0.2s ease;
    cursor: pointer;
    isolation: isolate;
  }

  .person-card:hover,
  .person-card:focus {
    transform: translateY(-2px);
    background: var(--card-bg-hover, rgb(15, 23, 42));
    border-color: var(
      --card-border-hover,
      var(--card-border, rgba(148, 163, 184, 0.2))
    );
    outline: none;
  }

  .person-thumb {
    width: 130px;
    aspect-ratio: 2 / 3;
    overflow: hidden;
    margin: 0;
    flex-shrink: 0;
    mix-blend-mode: lighten;
  }

  .person-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    mix-blend-mode: lighten;
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

  .thumb-fallback {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.75rem;
    font-weight: 600;
    color: rgba(148, 163, 184, 0.6);
    background: rgba(15, 23, 42, 0.5);
  }

  .card-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    align-items: center;
    text-align: center;
    margin-top: -1.25rem;
  }

  .card-name {
    font-family: var(--card-heading-font, inherit);
    font-size: 0.875rem;
    font-weight: 600;
    line-height: 1.2;
    color: var(--card-primary, #f8fafc);
    margin: 0;
    text-shadow:
      0 1px 4px rgba(0, 0, 0, 0.8),
      0 1px 2px rgba(0, 0, 0, 0.9);
  }

  .card-years {
    font-family: var(--card-body-font, inherit);
    font-size: 0.75rem;
    line-height: 1.3;
    color: var(--card-secondary, #38bdf8);
    margin: 0;
    font-weight: 500;
    text-shadow:
      0 1px 4px rgba(0, 0, 0, 0.8),
      0 1px 2px rgba(0, 0, 0, 0.9);
  }

  .card-roles {
    font-family: var(--card-body-font, inherit);
    font-size: 0.6875rem;
    line-height: 1.3;
    color: rgba(226, 232, 240, 0.8);
    margin: 0;
    opacity: 0.7;
    text-shadow:
      0 1px 4px rgba(0, 0, 0, 0.8),
      0 1px 2px rgba(0, 0, 0, 0.9);
  }

  @media (max-width: 640px) {
    .person-thumb {
      width: 110px;
    }

    .card-name {
      font-size: 0.8125rem;
    }

    .card-years,
    .card-roles {
      font-size: 0.6875rem;
    }
  }
</style>
