<script>
  import { currentLanguage } from "../stores/language";
  import { mdiBabyFaceOutline, mdiSkullOutline } from "@mdi/js";
  import { _ } from "../stores/language";
  import { push, location } from "svelte-spa-router";

  export let entries = [];
  export let getSummary = () => "";
  export let getStyle = () => ({});
  export let onSelectPerson = () => {};

  let showExplanation = false;
  let activeTags = new Set();
  let searchQuery = "";
  let loadedImages = new Set();

  function handleImageLoad(entryId) {
    loadedImages.add(entryId);
    loadedImages = loadedImages; // Trigger reactivity
  }

  function toggleExplanation() {
    showExplanation = !showExplanation;
  }

  function closeExplanation() {
    showExplanation = false;
  }

  function handleLanguageChange(event) {
    const newLang = event.target.value;
    // Strip query params from current path - history should only contain base paths
    const currentPath = $location.split('?')[0];

    // Build new URL with updated language
    let newPath;
    // Check if we're on landing page
    if (currentPath === '/' || currentPath === '') {
      newPath = `/${newLang}`;
    } else if (currentPath.match(/^\/[a-z]{2}\//)) {
      // Replace existing language in URL
      newPath = currentPath.replace(/^\/[a-z]{2}\//, `/${newLang}/`);
    } else {
      // Add language prefix to current path
      newPath = `/${newLang}${currentPath}`;
    }

    // Use push to create history entry (allows back button to undo language change)
    push(newPath);
  }

  // Normalize tag for comparison (lowercase, trim)
  function normalizeTag(tag) {
    return tag.trim().toLowerCase();
  }

  function toggleTag(normalizedTag) {
    if (activeTags.has(normalizedTag)) {
      activeTags.delete(normalizedTag);
    } else {
      activeTags.add(normalizedTag);
    }
    activeTags = activeTags; // Trigger reactivity
  }

  // Compute tag frequencies from entries (with case-insensitive grouping)
  $: tagFrequencies = (() => {
    const frequencies = new Map(); // normalized tag -> {display: string, count: number}
    entries.forEach((entry) => {
      if (Array.isArray(entry.primaryRoles)) {
        entry.primaryRoles.forEach((role) => {
          if (role && typeof role === "string") {
            const normalized = normalizeTag(role);
            const existing = frequencies.get(normalized);
            if (existing) {
              existing.count += 1;
            } else {
              frequencies.set(normalized, { display: role, count: 1 });
            }
          }
        });
      }
    });
    // Filter to only tags that cover at least 2 persons
    return new Map([...frequencies].filter(([_, data]) => data.count >= 2));
  })();

  // Get top 10 most frequent tags
  $: topTags = (() => {
    return [...tagFrequencies.entries()]
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, 10)
      .map(([normalizedTag, data]) => ({
        normalized: normalizedTag,
        display: data.display,
      }));
  })();

  // Check if entry was created in the last 7 days
  function isNewEntry(entry) {
    if (!entry.created) return false;
    try {
      const createdDate = new Date(entry.created);
      const now = new Date();
      const daysDiff = (now - createdDate) / (1000 * 60 * 60 * 24);
      return daysDiff <= 7;
    } catch {
      return false;
    }
  }

  // Check if entry has an anniversary (birth or death) within the next 3 days
  function getAnniversary(entry) {
    const now = new Date();
    const currentYear = now.getFullYear();
    const today = new Date(currentYear, now.getMonth(), now.getDate());

    const checkDate = (dateStr, type) => {
      if (!dateStr) return null;
      try {
        const date = new Date(dateStr);
        const month = date.getMonth();
        const day = date.getDate();
        const originalYear = date.getFullYear();

        // Create anniversary date for this year
        const anniversaryThisYear = new Date(currentYear, month, day);

        // Calculate days until anniversary
        const diffTime = anniversaryThisYear - today;
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

        // Check if within next 3 days (0-3 days inclusive)
        if (diffDays >= 0 && diffDays <= 3) {
          const years = currentYear - originalYear;
          return {
            type,
            date: anniversaryThisYear,
            years,
            daysUntil: diffDays,
          };
        }
      } catch {
        return null;
      }
      return null;
    };

    const birthAnniversary = checkDate(entry.birthDate, "birth");
    const deathAnniversary = checkDate(entry.deathDate, "death");

    // Return the closest anniversary
    if (birthAnniversary && deathAnniversary) {
      return birthAnniversary.daysUntil <= deathAnniversary.daysUntil
        ? birthAnniversary
        : deathAnniversary;
    }
    return birthAnniversary || deathAnniversary;
  }

  // Filter and sort entries based on active tags, search query, and last updated date
  $: filteredEntries = (() => {
    let result = entries;

    // Apply tag filters
    if (activeTags.size > 0) {
      result = result.filter((entry) => {
        if (!Array.isArray(entry.primaryRoles)) return false;
        return entry.primaryRoles.some((role) =>
          activeTags.has(normalizeTag(role))
        );
      });
    }

    // Apply search query filter
    if (searchQuery.trim()) {
      const query = searchQuery.trim().toLowerCase();
      result = result.filter((entry) => {
        // Search in name
        const name = displayName(entry.name || "").toLowerCase();
        if (name.includes(query)) return true;

        // Search in roles
        if (Array.isArray(entry.primaryRoles)) {
          if (
            entry.primaryRoles.some((role) =>
              role.toLowerCase().includes(query)
            )
          ) {
            return true;
          }
        }

        // Search in summary
        const summary = (
          entry.summary ||
          getSummary(entry) ||
          ""
        ).toLowerCase();
        if (summary.includes(query)) return true;

        return false;
      });
    }

    // Sort by anniversary first, then by lastUpdated
    result = [...result].sort((a, b) => {
      const anniversaryA = getAnniversary(a);
      const anniversaryB = getAnniversary(b);

      // Prioritize entries with anniversaries
      if (anniversaryA && !anniversaryB) return -1;
      if (!anniversaryA && anniversaryB) return 1;

      // If both have anniversaries, sort by days until anniversary
      if (anniversaryA && anniversaryB) {
        return anniversaryA.daysUntil - anniversaryB.daysUntil;
      }

      // Otherwise, sort by lastUpdated (most recent first)
      const dateA = a.lastUpdated ? new Date(a.lastUpdated).getTime() : 0;
      const dateB = b.lastUpdated ? new Date(b.lastUpdated).getTime() : 0;
      return dateB - dateA;
    });

    return result;
  })();

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function displayName(name = "") {
    if (typeof name !== "string") return "";
    return name.replace(/_/g, " ").replace(/\s+/g, " ").trim();
  }

  function formatLifespan(entry) {
    // Support both old 'lifespan' field and new 'birthDate'/'deathDate' fields
    if (entry.lifespan) {
      return entry.lifespan;
    }
    const birthYear = entry.birthDate ? entry.birthDate.substring(0, 4) : "?";
    const deathYear = entry.deathDate ? entry.deathDate.substring(0, 4) : "?";
    if (birthYear === "?" && deathYear === "?") {
      return null;
    }
    return `${birthYear}–${deathYear}`;
  }

  function handleSelect(id) {
    if (!id) return;
    onSelectPerson({ detail: id });
  }

  function summaryFor(entry) {
    return entry?.summary ?? getSummary(entry);
  }

  function initialsFromName(name = "") {
    const cleaned = displayName(name);
    const parts = cleaned
      .split(/\s+/)
      .map((segment) => segment.trim())
      .filter(Boolean);
    if (parts.length === 0) {
      return "";
    }
    if (parts.length === 1) {
      return parts[0].slice(0, 2).toUpperCase();
    }
    const first = parts[0].charAt(0).toUpperCase();
    const last = parts[parts.length - 1].charAt(0).toUpperCase();
    return `${first}${last}`;
  }

  function getThumbnailUrl(imageUrl, width = 200) {
    if (!imageUrl || typeof imageUrl !== "string") return imageUrl;

    // Optimize Wikimedia Commons images
    if (imageUrl.includes("upload.wikimedia.org/wikipedia/commons/")) {
      // Convert full URL to thumbnail URL
      // Example: https://upload.wikimedia.org/wikipedia/commons/a/b/File.jpg
      // becomes: https://upload.wikimedia.org/wikipedia/commons/thumb/a/b/File.jpg/200px-File.jpg
      const parts = imageUrl.split("/wikipedia/commons/");
      if (parts.length === 2) {
        const [base, path] = parts;
        const filename = path.split("/").pop();
        return `${base}/wikipedia/commons/thumb/${path}/${width}px-${filename}`;
      }
    }

    // Return original URL for non-Wikimedia images
    return imageUrl;
  }

  function cardStyleVars(style) {
    if (!style || typeof style !== "object") return "";
    const segments = [];
    if (style.background) segments.push(`--card-bg: ${style.background}`);
    if (style.primary) segments.push(`--card-primary: ${style.primary}`);
    if (style.secondary) segments.push(`--card-secondary: ${style.secondary}`);
    if (style.backgroundPatternDataUrl) {
      segments.push(
        `--card-pattern-image: url("${style.backgroundPatternDataUrl}")`
      );
      segments.push(`--card-pattern-size: 500px`);
    }
    if (typeof style.patternOpacity === "number") {
      const opacity = clamp(style.patternOpacity, 0, 1);
      segments.push(`--card-pattern-opacity: ${opacity}`);
    }
    if (style.headingFont) {
      segments.push(
        `--card-heading-font: "${style.headingFont}", Inter, sans-serif`
      );
    }
    if (style.bodyFont) {
      segments.push(`--card-body-font: "${style.bodyFont}", Inter, sans-serif`);
    }
    return segments.join("; ");
  }

  function joinWithSeparator(items, styleConfig) {
    if (!items || items.length === 0) return "";
    if (items.length === 1) return items[0];

    // Use separator_glyph_svg if available
    if (styleConfig?.separatorGlyphSvg) {
      return items.join(`<span class="separator-glyph" style="display: inline-block; margin: 0 0.5rem; width: 1em; height: 1em; vertical-align: middle; background: url('${styleConfig.separatorGlyphDataUrl}') center/contain no-repeat;"></span>`);
    }

    // Fallback to middle dot
    return items.join(" · ");
  }
</script>

<section class="landing">
  <div class="top-controls">
      <select
        value={$currentLanguage}
        on:change={handleLanguageChange}
        aria-label={$_("app.select_language")}
        class="language-selector"
      >
        <option value="en">English</option>
        <option value="de">Deutsch</option>
      </select>
      <button
        class="ai-disclaimer-button"
        on:click={toggleExplanation}
        aria-label={$_("landing.learn_about_ai")}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="16"
          height="16"
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
    </div>

  <div class="header-container">
    <div class="landing-hero">
      <p class="eyebrow">{$_("app.title")}</p>
      <h1>{$_("app.tagline")}</h1>
    </div>
    <div class="filters-section">
      <div class="search-box">
        <svg
          class="search-icon"
          xmlns="http://www.w3.org/2000/svg"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <circle cx="11" cy="11" r="8"></circle>
          <path d="m21 21-4.35-4.35"></path>
        </svg>
        <input
          type="text"
          class="search-input"
          placeholder={$_("landing.search_placeholder")}
          bind:value={searchQuery}
        />
        {#if searchQuery}
          <button
            class="clear-search"
            on:click={() => {
              searchQuery = "";
            }}
            aria-label={$_("landing.clear_search")}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        {/if}
      </div>
      {#if topTags.length > 0}
        <div class="tag-filters">
          <div class="tag-filters-header">
            <span class="filter-label">{$_("landing.filter_by_role")}</span>
            {#if activeTags.size > 0}
              <button
                class="clear-filters"
                on:click={() => {
                  activeTags = new Set();
                }}
              >
                {$_("landing.clear_all")}
              </button>
            {/if}
          </div>
          <div class="tag-chips">
            {#each topTags as tag (tag.normalized)}
              <button
                class="tag-chip"
                class:active={activeTags.has(tag.normalized)}
                on:click={() => toggleTag(tag.normalized)}
                aria-pressed={activeTags.has(tag.normalized)}
              >
                {tag.display}
                <span class="tag-count"
                  >{tagFrequencies.get(tag.normalized).count}</span
                >
              </button>
            {/each}
          </div>
        </div>
      {/if}
    </div>
  </div>
  <div class="landing-grid">
    {#if filteredEntries.length > 0}
      {#each filteredEntries as entry (entry.id)}
        {@const summary = summaryFor(entry)}
        {@const style = entry.style ?? getStyle(entry.id)}
        {@const lifespan = formatLifespan(entry)}
        {@const anniversary = getAnniversary(entry)}
        <article
          class="person-card"
          style={cardStyleVars(style)}
          on:click={() => handleSelect(entry.id)}
          on:keydown={(e) =>
            (e.key === "Enter" || e.key === " ") && handleSelect(entry.id)}
          role="button"
          tabindex="0"
          aria-label={`Open life story for ${displayName(entry.name)}`}
        >
          {#if anniversary}
            <span
              class="anniversary-badge"
              title={`${anniversary.years} years since ${anniversary.type}`}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="14"
                height="14"
                viewBox="0 0 24 24"
              >
                <path
                  fill="currentColor"
                  d={anniversary.type === "birth"
                    ? mdiBabyFaceOutline
                    : mdiSkullOutline}
                />
              </svg>
              {#if anniversary.daysUntil === 0}
                {$_("landing.updated_today")}
              {:else if anniversary.daysUntil === 1}
                {$_("landing.updated_yesterday")}
              {:else}
                {$_("landing.updated_days_ago", {
                  days: anniversary.daysUntil,
                })}
              {/if}
              · {$_("landing.anniversary_years", { years: anniversary.years })}
            </span>
          {:else if isNewEntry(entry)}
            <span class="new-badge">{$_("landing.new_label")}</span>
          {/if}
          <figure class="person-thumb">
            {#if entry?.portrait?.image}
              <img
                src={getThumbnailUrl(entry.portrait.image, 200)}
                srcset={`${getThumbnailUrl(entry.portrait.image, 200)} 1x, ${getThumbnailUrl(entry.portrait.image, 400)} 2x`}
                alt={loadedImages.has(entry.id)
                  ? entry.portrait.alt ?? `Portrait of ${displayName(entry.name)}`
                  : ""}
                loading="lazy"
                decoding="async"
                on:load={() => handleImageLoad(entry.id)}
              />
            {:else}
              <div class="thumb-fallback" aria-hidden="true">
                {initialsFromName(entry.name)}
              </div>
            {/if}
          </figure>
          <div class="card-body">
            <div class="card-header">
              <h2>{displayName(entry.name)}</h2>
              {#if lifespan}
                <p class="card-meta">
                  <span class="meta-years">{lifespan}</span>
                </p>
              {/if}
              {#if (entry.primaryRoles?.length ?? 0) > 0}
                <p class="card-meta">
                  <span class="meta-roles"
                    >{@html joinWithSeparator(entry.primaryRoles, style)}</span
                  >
                </p>
              {/if}
            </div>
            {#if summary}
              <p class="card-summary">{summary}</p>
            {:else}
              <p class="card-summary placeholder">
                A summary is not available yet, but the timeline is ready.
              </p>
            {/if}
          </div>
        </article>
      {/each}
    {:else if entries.length === 0}
      <p class="landing-empty">
        {$_("landing.empty_message")}
      </p>
    {:else}
      <p class="landing-empty">No persons match the selected filters.</p>
    {/if}
  </div>
</section>

{#if showExplanation}
  <div class="modal-backdrop" on:click={closeExplanation}>
    <div class="modal-content" on:click|stopPropagation>
      <button
        class="modal-close"
        on:click={closeExplanation}
        aria-label={$_("landing.ai_modal_close")}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>
      <h2>{$_("landing.ai_modal_title")}</h2>
      <div class="modal-body">
        <p>
          <strong>{$_("landing.ai_how_it_works")}</strong>
          {$_("landing.ai_description")}
        </p>
        <ul>
          <li>{$_("landing.ai_step_1")}</li>
          <li>{$_("landing.ai_step_2")}</li>
          <li>{$_("landing.ai_step_3")}</li>
          <li>{$_("landing.ai_step_4")}</li>
          <li>{$_("landing.ai_step_5")}</li>
        </ul>
        <p>
          <strong>{$_("landing.ai_accuracy")}</strong>
          {$_("landing.ai_accuracy_text")}
        </p>
        <p>
          <strong>{$_("landing.ai_privacy")}</strong>
          {$_("landing.ai_privacy_text")}
        </p>
      </div>
    </div>
  </div>
{/if}

<style>
  .landing {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    padding: 1rem 1.5rem 4rem;
    background: linear-gradient(
      180deg,
      rgba(15, 23, 42, 0.94) 0%,
      rgba(15, 23, 42, 0.9) 35%,
      rgba(15, 23, 42, 0.82) 100%
    );
    position: relative;
  }

  .top-controls {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-bottom: 0;
    justify-content: flex-end;
  }

  .language-selector {
    padding: 0.5rem 0.75rem;
    background: rgba(15, 23, 42, 0.9);
    border: 1px solid rgba(226, 232, 240, 0.2);
    border-radius: 0.375rem;
    color: #e2e8f0;
    font-size: 0.875rem;
    font-family: inherit;
    cursor: pointer;
    backdrop-filter: blur(8px);
    transition: all 0.2s ease;
  }

  .language-selector:hover {
    background: rgba(15, 23, 42, 1);
    border-color: rgba(226, 232, 240, 0.4);
  }

  .language-selector:focus {
    outline: 2px solid #38bdf8;
    outline-offset: 2px;
  }

  .language-selector option {
    background: #0f172a;
    color: #e2e8f0;
  }

  .ai-disclaimer-button {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.5rem 0.75rem;
    border-radius: 0.5rem;
    background: rgba(251, 191, 36, 0.12);
    border: 1px solid rgba(251, 191, 36, 0.3);
    color: #fbbf24;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .ai-disclaimer-button:hover {
    background: rgba(251, 191, 36, 0.18);
    border-color: rgba(251, 191, 36, 0.45);
  }

  .ai-disclaimer-button svg {
    flex-shrink: 0;
    opacity: 0.9;
  }

  .header-container {
    display: flex;
    flex-direction: column;
    gap: 2rem;
  }

  .landing-hero {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    max-width: 60ch;
  }

  .landing-hero h1 {
    font-size: 2.1rem;
    margin: 0;
    line-height: 1.15;
  }

  .landing-hero p {
    margin: 0;
    font-size: 1rem;
    color: #cbd5f5;
  }

  .landing-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 1.5rem;
    grid-auto-rows: 1fr;
  }

  .landing-empty {
    margin: 0;
    font-size: 1rem;
    color: #94a3b8;
  }

  .person-card {
    position: relative;
    display: grid;
    grid-template-columns: 82px 1fr;
    align-items: stretch;
    gap: 1rem;
    padding: 1.25rem 1.35rem;
    border-radius: 1rem;
    background-color: var(--card-bg, rgba(15, 23, 42, 0.94));
    border: 1px solid rgba(148, 163, 184, 0.18);
    box-shadow: 0 14px 32px rgba(15, 23, 42, 0.32);
    transition:
      transform 0.22s ease,
      border-color 0.22s ease,
      box-shadow 0.22s ease;
    min-height: 0;
    overflow: hidden;
    color: #e2e8f0;
    isolation: isolate;
    cursor: pointer;
  }

  .person-card::before,
  .person-card::after {
    content: "";
    position: absolute;
    inset: 0;
    border-radius: inherit;
    pointer-events: none;
    z-index: 0;
  }

  .person-card::before {
    background-image: var(--card-pattern-image, none);
    background-size: var(--card-pattern-size, 400px);
    background-repeat: repeat;
    opacity: var(--card-pattern-opacity, 0.85);
    mix-blend-mode: overlay;
  }

  .person-card::after {
    background: linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.04) 0%,
      rgba(0, 0, 0, 0.48) 100%
    );
  }

  .person-card:hover,
  .person-card:focus-within {
    transform: translateY(-4px);
    border-color: var(--card-secondary, rgba(56, 189, 248, 0.45));
    box-shadow: 0 18px 36px rgba(15, 23, 42, 0.42);
  }

  .person-card:active {
    transform: translateY(-2px) scale(0.98);
    transition:
      transform 0.1s ease,
      border-color 0.1s ease,
      box-shadow 0.1s ease;
  }

  .person-card > * {
    position: relative;
    z-index: 1;
  }

  .person-thumb {
    margin: 0;
    width: 82px;
    height: 82px;
    border-radius: 0.9rem;
    overflow: hidden;
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(148, 163, 184, 0.2);
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
  }

  .person-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: top;
    display: block;
  }

  .person-thumb img[alt=""] {
    visibility: hidden;
  }

  .thumb-fallback {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    background: radial-gradient(
        circle at 30% 30%,
        var(--card-secondary, rgba(56, 189, 248, 0.35)),
        transparent 70%
      ),
      rgba(30, 41, 59, 0.82);
    color: var(--card-secondary, #e0f2fe);
    font-weight: 700;
    font-size: 1.2rem;
    letter-spacing: 0.08em;
  }

  .card-body {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    min-width: 0;
  }

  .card-header {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .person-card h2 {
    margin: 0;
    font-size: 1.2rem;
    line-height: 1.2;
    color: var(--card-primary, #f8fafc);
    font-family: var(--card-heading-font, Inter, sans-serif);
  }

  .new-badge {
    position: absolute;
    top: -0.5rem;
    right: -0.5rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.5rem 0.75rem 0.25rem 0.55rem;
    border-radius: 0.4rem;
    background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
    border: 2px solid rgba(255, 255, 255, 0.2);
    box-shadow:
      0 2px 8px rgba(34, 197, 94, 0.3),
      0 4px 12px rgba(0, 0, 0, 0.2);
    color: #ffffff;
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    z-index: 10;
    transform: rotate(3deg);
    transition: transform 0.2s ease;
  }

  .person-card:hover .new-badge {
    transform: rotate(0deg) scale(1.05);
  }

  .anniversary-badge {
    position: absolute;
    top: -0.5rem;
    right: -0.5rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.35rem;
    padding: 0.5rem 0.75rem 0.25rem 0.55rem;
    border-radius: 0.4rem;
    background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
    border: 2px solid rgba(255, 255, 255, 0.2);
    box-shadow:
      0 2px 8px rgba(245, 158, 11, 0.3),
      0 4px 12px rgba(0, 0, 0, 0.2);
    color: #ffffff;
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: 0.04em;
    z-index: 10;
    transform: rotate(-2deg);
    transition: transform 0.2s ease;
  }

  .anniversary-badge svg {
    flex-shrink: 0;
  }

  .person-card:hover .anniversary-badge {
    transform: rotate(0deg) scale(1.05);
  }

  .card-meta {
    margin: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    font-size: 0.8rem;
    color: rgba(148, 163, 184, 0.85);
    font-family: var(--card-body-font, Inter, sans-serif);
  }

  .card-meta .meta-separator {
    color: rgba(148, 163, 184, 0.65);
  }

  .card-meta .meta-years {
    color: var(--card-secondary, rgba(148, 163, 184, 0.85));
    font-weight: 500;
  }

  .card-meta .meta-roles {
    color: var(--card-secondary, rgba(148, 163, 184, 0.85));
    text-transform: uppercase;
    font-size: 0.7rem;
  }

  .card-summary {
    margin: 0;
    font-size: 0.92rem;
    color: rgba(203, 213, 225, 0.92);
    line-height: 1.45;
    display: -webkit-box;
    -webkit-line-clamp: 4;
    -webkit-box-orient: vertical;
    overflow: hidden;
    font-family: var(--card-body-font, Inter, sans-serif);
  }

  .card-summary.placeholder {
    color: #94a3b8;
    font-style: italic;
  }

  .eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.75rem;
    color: var(--card-secondary, rgba(56, 189, 248, 0.9));
    margin: 0;
  }

  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
  }

  .modal-content {
    position: relative;
    max-width: 600px;
    width: 100%;
    background: rgba(15, 23, 42, 0.95);
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 1rem;
    padding: 2rem;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  }

  .modal-close {
    position: absolute;
    top: 1rem;
    right: 1rem;
    padding: 0.5rem;
    border-radius: 0.5rem;
    background: transparent;
    border: none;
    color: #94a3b8;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
  }

  .modal-close:hover {
    background: rgba(148, 163, 184, 0.15);
    color: #cbd5e1;
  }

  .modal-content h2 {
    margin: 0 0 1.25rem 0;
    font-size: 1.5rem;
    color: #fbbf24;
  }

  .modal-body {
    font-size: 0.95rem;
    line-height: 1.6;
    color: #cbd5e1;
  }

  .modal-body strong {
    color: #fbbf24;
  }

  .modal-body p {
    margin: 0 0 0.75rem 0;
  }

  .modal-body p:last-child {
    margin-bottom: 0;
  }

  .modal-body ul {
    margin: 0.75rem 0;
    padding-left: 1.5rem;
  }

  .modal-body li {
    margin-bottom: 0.5rem;
  }

  .modal-body li:last-child {
    margin-bottom: 0;
  }

  .filters-section {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .search-box {
    position: relative;
    display: flex;
    align-items: center;
    width: 100%;
    max-width: 600px;
  }

  .search-icon {
    position: absolute;
    left: 1rem;
    color: #94a3b8;
    pointer-events: none;
  }

  .search-input {
    width: 100%;
    padding: 0.75rem 1rem 0.75rem 2.75rem;
    border-radius: 0.5rem;
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid rgba(148, 163, 184, 0.25);
    color: #e2e8f0;
    font-size: 0.95rem;
    font-family: inherit;
    transition: all 0.2s ease;
  }

  .search-input::placeholder {
    color: #64748b;
  }

  .search-input:focus {
    outline: none;
    background: rgba(30, 41, 59, 0.8);
    border-color: rgba(56, 189, 248, 0.5);
    box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.1);
  }

  .clear-search {
    position: absolute;
    right: 0.75rem;
    padding: 0.35rem;
    border-radius: 0.25rem;
    background: transparent;
    border: none;
    color: #94a3b8;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
  }

  .clear-search:hover {
    background: rgba(148, 163, 184, 0.15);
    color: #cbd5e1;
  }

  .tag-filters {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .tag-filters-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    min-height: 2rem;
  }

  .filter-label {
    font-size: 0.9rem;
    font-weight: 500;
    color: #cbd5e1;
    flex-shrink: 0;
  }

  .clear-filters {
    padding: 0.35rem 0.75rem;
    border-radius: 0.375rem;
    background: rgba(148, 163, 184, 0.12);
    border: 1px solid rgba(148, 163, 184, 0.25);
    color: #94a3b8;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .clear-filters:hover {
    background: rgba(148, 163, 184, 0.18);
    border-color: rgba(148, 163, 184, 0.4);
    color: #cbd5e1;
  }

  .tag-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.65rem;
  }

  .tag-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.85rem;
    border-radius: 0.5rem;
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(148, 163, 184, 0.25);
    color: #cbd5e1;
    font-size: 0.75rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;
    text-transform: uppercase;
  }

  .tag-chip:hover {
    background: rgba(15, 23, 42, 0.95);
    border-color: rgba(148, 163, 184, 0.4);
    color: #e2e8f0;
  }

  .tag-chip.active {
    background: rgba(56, 189, 248, 0.15);
    border-color: rgba(56, 189, 248, 0.5);
    color: #38bdf8;
  }

  .tag-chip.active:hover {
    background: rgba(56, 189, 248, 0.2);
    border-color: rgba(56, 189, 248, 0.65);
  }

  .tag-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 1.35rem;
    height: 1.35rem;
    padding: 0 0.35rem;
    border-radius: 0.35rem;
    background: rgba(148, 163, 184, 0.2);
    font-size: 0.75rem;
    font-weight: 600;
    color: #cbd5e1;
  }

  .tag-chip.active .tag-count {
    background: rgba(56, 189, 248, 0.3);
    color: #e0f2fe;
  }

  @media (max-width: 480px) {
    .person-card {
      grid-template-columns: 70px 1fr;
      padding: 1.1rem 1.2rem;
    }

    .person-thumb {
      width: 70px;
      height: 70px;
    }
  }

  @media (min-width: 768px) {
    .landing {
      padding: 4rem 3rem 5rem;
      gap: 3rem;
    }

    .ai-disclaimer-button {
      top: 2.5rem;
      right: 2.5rem;
    }

    .header-container {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 3rem;
      align-items: start;
    }

    .landing-hero {
      max-width: none;
    }

    .landing-hero h1 {
      font-size: 2.6rem;
    }

    .filters-section {
      padding-top: 2.5rem;
    }

    .landing-grid {
      gap: 2rem;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    }

    .person-card {
      padding: 1.5rem 1.75rem;
      grid-template-columns: 92px 1fr;
    }

    .person-thumb {
      width: 92px;
      height: 92px;
    }

    .person-card h2 {
      font-size: 1.3rem;
    }
  }
</style>
