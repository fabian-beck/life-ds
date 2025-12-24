<script>
  import { _ } from "../stores/language";
  import { displayName, joinWithSeparator } from "../utils/helpers.js";
  import { computeYearsLabel, getThumbnailUrl } from "../utils/storyHelpers.js";

  export let conclusion = null;
  export let relatedPersons = [];
  export let personStyle = null;
  export let personStylesRegistry = null;

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

  // Get style for a specific person
  function getPersonStyle(personId) {
    if (!personStylesRegistry || !personId) return null;
    return personStylesRegistry[personId] || null;
  }
</script>

<div class="content conclusion-content">
  <div class="conclusion-box">
    <h2 class="conclusion-headline">{$_("conclusion.title")}</h2>

    {#if conclusion}
      <p class="conclusion-text">{conclusion}</p>
    {/if}

    {#if relatedPersons.length > 0}
      <div class="related-section">
        <h3 class="related-headline">{$_("conclusion.related_persons")}</h3>
        <div class="related-persons-grid">
          {#each relatedPersons as { person } (person.id)}
            {@const lifespan = formatLifespan(person)}
            {@const relatedPersonStyle = getPersonStyle(person.id)}
            {@const roles = Array.isArray(person.primaryRoles)
              ? joinWithSeparator(person.primaryRoles, relatedPersonStyle)
              : ""}
            <a
              href="#/story/{person.id}"
              class="related-person-card"
              style="--card-primary: {relatedPersonStyle?.primary || '#f8fafc'}; --card-secondary: {relatedPersonStyle?.secondary || '#38bdf8'}; --card-heading-font: {relatedPersonStyle?.headingFont ? `'${relatedPersonStyle.headingFont}', sans-serif` : 'var(--story-heading-font, sans-serif)'}; --card-body-font: {relatedPersonStyle?.bodyFont ? `'${relatedPersonStyle.bodyFont}', sans-serif` : 'var(--story-body-font, sans-serif)'};"
              aria-label={`Open life story for ${displayName(person.name)}`}
            >
              {#if person?.portrait?.image}
                <figure class="person-thumb">
                  <img
                    src={getThumbnailUrl(person.portrait.image, 120)}
                    srcset={`${getThumbnailUrl(person.portrait.image, 120)} 1x, ${getThumbnailUrl(person.portrait.image, 240)} 2x`}
                    alt=""
                    loading="lazy"
                    decoding="async"
                  />
                </figure>
              {:else}
                <figure class="person-thumb">
                  <div class="thumb-fallback" aria-hidden="true">
                    {initialsFromName(person.name)}
                  </div>
                </figure>
              {/if}
              <div class="card-info">
                <h4 class="card-name">{displayName(person.name)}</h4>
                {#if lifespan}
                  <p class="card-years">{lifespan}</p>
                {/if}
                {#if roles}
                  <p class="card-roles">{@html roles}</p>
                {/if}
              </div>
            </a>
          {/each}
        </div>
      </div>
    {/if}
  </div>
</div>

<style>
  .content {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    position: relative;
    z-index: 4;
    align-self: center;
    width: min(54rem, 100%);
    margin: 0 auto;
  }

  .conclusion-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.8rem;
    padding-top: clamp(0rem, 8vh, 10rem);
  }

  .conclusion-box {
    max-width: 42rem;
    width: 100%;
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.5rem;
    padding: 2rem;
    isolation: isolate;
  }

  .conclusion-headline {
    font-family: var(--story-heading-font, sans-serif);
    font-size: clamp(1.25rem, 3.5vw, 1.75rem);
    font-weight: 700;
    line-height: 1.2;
    color: var(--story-secondary, #38bdf8);
    margin: 0;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .conclusion-text {
    font-family: var(--story-body-font, sans-serif);
    font-size: clamp(1rem, 2.2vw, 1.125rem);
    font-style: italic;
    line-height: 1.7;
    color: #e2e8f0;
    margin: 0;
    max-width: 38rem;
    text-wrap: balance;
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .related-section {
    margin-top: 1rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    width: 100%;
  }

  .related-headline {
    font-family: var(--story-heading-font, sans-serif);
    font-size: clamp(0.875rem, 2vw, 1rem);
    font-weight: 600;
    line-height: 1.3;
    color: var(--story-primary, #f8fafc);
    margin: 0;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    opacity: 0.9;
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .related-persons-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 1rem;
    width: 100%;
    max-width: 600px;
  }

  .related-person-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0;
    padding: 0.375rem 0.75rem 1rem;
    background: rgba(15, 23, 42, 0.95);
    border-radius: 0.5rem;
    border: 1px solid rgba(148, 163, 184, 0.2);
    text-decoration: none;
    color: inherit;
    transition:
      transform 0.2s ease,
      background 0.2s ease,
      border-color 0.2s ease;
    cursor: pointer;
    isolation: isolate;
  }

  .related-person-card:hover,
  .related-person-card:focus {
    transform: translateY(-2px);
    background: rgb(15, 23, 42);
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
    font-family: var(--card-heading-font, var(--story-heading-font, sans-serif));
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
    font-family: var(--card-body-font, var(--story-body-font, sans-serif));
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
    font-family: var(--card-body-font, var(--story-body-font, sans-serif));
    font-size: 0.75rem;
    line-height: 1.3;
    color: rgba(226, 232, 240, 0.8);
    margin: 0;
    text-shadow:
      0 1px 4px rgba(0, 0, 0, 0.8),
      0 1px 2px rgba(0, 0, 0, 0.9);
  }

  .card-roles {
    font-size: 0.6875rem;
    opacity: 0.7;
  }

  @media (max-width: 640px) {
    .conclusion-box {
      gap: 1.25rem;
      padding: 1.25rem;
    }

    .conclusion-headline {
      font-size: clamp(1.1rem, 5vw, 1.5rem);
    }

    .conclusion-text {
      font-size: clamp(0.9rem, 3.5vw, 1rem);
    }

    .related-headline {
      font-size: 0.8rem;
    }

    .related-persons-grid {
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 0.75rem;
    }

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
