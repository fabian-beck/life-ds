<script>
  import { onMount, onDestroy, tick } from "svelte";
  import { currentLanguage } from "../stores/language";
  import { mdiBabyFaceOutline, mdiSkullOutline } from "@mdi/js";
  import { _ } from "../stores/language";
  import { push } from "svelte-spa-router";
  import { location } from "../stores/router.js";
  import { clamp, displayName } from "../utils/helpers.js";
  import { getThumbnailUrl } from "../utils/storyHelpers.js";
  import { slide, fade } from "svelte/transition";
  import AIDisclaimerModal from "./AIDisclaimerModal.svelte";
  import AIGeneratedButton from "./AIGeneratedButton.svelte";
  import HighContrastToggle from "./HighContrastToggle.svelte";
  import MetaStoryCarousel from "./MetaStoryCarousel.svelte";
  import SeparatedList from "./SeparatedList.svelte";
  // LandingMap is imported on demand where it is rendered: it pulls in MapLibre
  // and its basemap dependencies (~1.1 MB), and the map starts collapsed.

  export let entries = [];
  export let englishEntries = []; // English registry entries for carousel portraits
  export let metaStories = [];
  export let getSummary = () => "";
  export let getStyle = () => ({});
  export let onSelectPerson = () => {};

  let showExplanation = false;
  let activeTags = new Set();
  let searchQuery = "";
  let loadedImages = new Set();
  let activeMetaStoryFilter = null;
  let showMap = false;
  let filtersSectionElement = null;
  let searchInputElement = null;
  let wasFiltering = false;

  // Sticky header state
  let showStickyHeader = false;
  let stickyHeaderElement = null;
  let stickyHeaderHeight = 0;
  const headerScrollThreshold = 200; // pixels scrolled before showing sticky header

  function handleScroll() {
    const scrollY = window.scrollY;
    showStickyHeader = scrollY > headerScrollThreshold;
  }

  // Update sticky header height when it appears/changes
  $: if (stickyHeaderElement && showStickyHeader) {
    stickyHeaderHeight = stickyHeaderElement.offsetHeight;
    if (typeof document !== "undefined") {
      document.documentElement.style.setProperty(
        "--landing-sticky-header-height",
        `${stickyHeaderHeight}px`
      );
    }
  } else {
    stickyHeaderHeight = 0;
    if (typeof document !== "undefined") {
      document.documentElement.style.setProperty(
        "--landing-sticky-header-height",
        "0px"
      );
    }
  }

  onMount(() => {
    window.addEventListener("scroll", handleScroll, { passive: true });
  });

  onDestroy(() => {
    window.removeEventListener("scroll", handleScroll);
  });

  function handleImageLoad(entryId) {
    loadedImages.add(entryId);
    loadedImages = new Set(loadedImages); // Trigger reactivity
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
    const currentPath = $location.split("?")[0];

    // Build new URL with updated language
    let newPath;
    // Check if we're on landing page (root)
    if (currentPath === "/" || currentPath === "") {
      newPath = `/${newLang}`;
    } else if (currentPath.match(/^\/[a-z]{2}(?:\/|$)/)) {
      // Replace existing language in URL (handles both /en and /en/story/...)
      newPath = currentPath.replace(/^\/[a-z]{2}/, `/${newLang}`);
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

  function getFilterTag(role, language, knownRoles) {
    const normalized = normalizeTag(role);

    if (language !== "de") {
      return { normalized, display: role };
    }

    // Merge a German masculine/feminine pair only when both forms actually
    // occur in the data. This avoids treating unrelated words ending in
    // "in" as gendered role names.
    if (normalized.endsWith("in")) {
      const masculine = normalized.slice(0, -2);
      if (knownRoles.has(masculine)) {
        return {
          normalized: masculine,
          display: `${knownRoles.get(masculine)}:in`,
        };
      }
    } else if (knownRoles.has(`${normalized}in`)) {
      return { normalized, display: `${role}:in` };
    }

    return { normalized, display: role };
  }

  function toggleTag(normalizedTag) {
    if (activeTags.has(normalizedTag)) {
      activeTags.delete(normalizedTag);
    } else {
      activeTags.add(normalizedTag);
    }
    activeTags = new Set(activeTags); // Trigger reactivity
  }

  function clearFilters() {
    searchQuery = "";
    activeTags = new Set();
    activeMetaStoryFilter = null;
  }

  $: knownRoles = new Map(
    entries.flatMap((entry) =>
      Array.isArray(entry.primaryRoles)
        ? entry.primaryRoles
            .filter((role) => role && typeof role === "string")
            .map((role) => [normalizeTag(role), role])
        : []
    )
  );

  // Compute tag frequencies from entries (with case-insensitive grouping and
  // merged masculine/feminine role names in German).
  $: tagFrequencies = (() => {
    const frequencies = new Map(); // normalized tag -> {display: string, count: number}
    entries.forEach((entry) => {
      if (Array.isArray(entry.primaryRoles)) {
        const entryTags = new Map();
        entry.primaryRoles.forEach((role) => {
          if (role && typeof role === "string") {
            const tag = getFilterTag(role, $currentLanguage, knownRoles);
            entryTags.set(tag.normalized, tag.display);
          }
        });
        entryTags.forEach((display, normalized) => {
          const existing = frequencies.get(normalized);
          if (existing) {
            existing.count += 1;
          } else {
            frequencies.set(normalized, { display, count: 1 });
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

  // Filter and sort entries based on active tags, search query, meta story filter, and last updated date
  $: filteredEntries = (() => {
    let result = entries;

    // Apply meta story filter first (takes precedence)
    if (activeMetaStoryFilter) {
      const metaStoryPersonIds = new Set(
        activeMetaStoryFilter.person_ids || []
      );
      result = result.filter((entry) => metaStoryPersonIds.has(entry.id));
    } else {
      // Apply tag filters only if no meta story filter is active
      if (activeTags.size > 0) {
        result = result.filter((entry) => {
          if (!Array.isArray(entry.primaryRoles)) return false;
          return entry.primaryRoles.some((role) => {
            const tag = getFilterTag(role, $currentLanguage, knownRoles);
            return activeTags.has(tag.normalized);
          });
        });
      }

      // Apply search query filter only if no meta story filter is active
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

  $: resultCountText = `${filteredEntries.length} ${filteredEntries.length === 1 ? $_("landing.result_one") : $_("landing.result_other")}`;
  $: isSearching = searchQuery.trim().length > 0;
  $: isFiltering =
    isSearching || activeTags.size > 0 || activeMetaStoryFilter !== null;

  // When search or filtering becomes active, scroll down to the filters section
  // (the meta-story carousel and title stay in place, just above the fold).
  $: if (isFiltering && !wasFiltering) {
    wasFiltering = true;
    scrollToFilters();
  } else if (!isFiltering && wasFiltering) {
    wasFiltering = false;
  }

  async function scrollToFilters() {
    if (typeof window === "undefined" || !filtersSectionElement) return;
    // The sticky header appears once we scroll past its threshold and would
    // otherwise cover the top of the filters section. Render it first so we can
    // measure its height and reserve room for it in the scroll target.
    showStickyHeader = true;
    await tick();
    const headerOffset = stickyHeaderElement?.offsetHeight ?? 0;
    const targetTop =
      filtersSectionElement.getBoundingClientRect().top +
      window.scrollY -
      headerOffset -
      16;
    window.scrollTo({ top: Math.max(0, targetTop), behavior: "smooth" });
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

  function handleFilterByMetaStory(metaStory) {
    // Toggle filter - if same meta story is clicked again, clear the filter
    if (activeMetaStoryFilter?.id === metaStory.id) {
      activeMetaStoryFilter = null;
    } else {
      activeMetaStoryFilter = metaStory;
    }
    // Clear search query and tag filters when filtering by meta story
    searchQuery = "";
    activeTags = new Set();
  }

  function handleExploreMetaStory(metaStory) {
    // Navigate to meta story view
    push(`/${$currentLanguage}/meta/${metaStory.id}`);
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
</script>

<section class="landing">
  <button
    type="button"
    class="skip-link"
    on:click={() => searchInputElement?.focus()}
  >
    {$_("landing.skip_to_search")}
  </button>
  <!-- Sticky header - appears when scrolling down -->
  {#if showStickyHeader}
    <div class="sticky-header-group" transition:fade={{ duration: 200 }}>
      <header class="landing-sticky-header" bind:this={stickyHeaderElement}>
        <div class="sticky-center">
          <span class="sticky-title">{$_("app.title")}</span>
        </div>
        <div class="sticky-right">
          <select
            value={$currentLanguage}
            on:change={handleLanguageChange}
            aria-label={$_("app.select_language")}
            class="language-selector sticky"
          >
            <option value="en">English</option>
            <option value="de">Deutsch</option>
          </select>
          <HighContrastToggle variant="sticky" />
        </div>
      </header>
      <div class="sticky-ai-button">
        <AIGeneratedButton variant="small" onClick={toggleExplanation} />
      </div>
    </div>
  {/if}

  <div class="top-controls">
    <AIGeneratedButton variant="large" onClick={toggleExplanation} />
    <div class="top-controls-right">
      <select
        value={$currentLanguage}
        on:change={handleLanguageChange}
        aria-label={$_("app.select_language")}
        class="language-selector"
      >
        <option value="en">English</option>
        <option value="de">Deutsch</option>
      </select>
      <HighContrastToggle />
    </div>
  </div>

  <div class="header-container">
    <div class="landing-hero">
      <p class="eyebrow">{$_("app.title")}</p>
      <h1>{$_("app.tagline")}</h1>
      <p class="hero-intro">{$_("landing.intro_text")}</p>
    </div>
    {#key $currentLanguage}
      <MetaStoryCarousel
        {metaStories}
        persons={englishEntries}
        onSelectPerson={handleSelect}
        onFilterByMetaStory={handleFilterByMetaStory}
        onExploreMetaStory={handleExploreMetaStory}
      />
    {/key}
  </div>

  <div class="filters-section" bind:this={filtersSectionElement}>
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
        bind:this={searchInputElement}
        bind:value={searchQuery}
        aria-label={$_("landing.search_label")}
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
    <div class="filters-right">
      {#if activeMetaStoryFilter}
        <div class="tag-filters">
          <div class="tag-filters-header">
            <span class="filter-label"
              >{$_("landing.filtered_by")}: {activeMetaStoryFilter.title}</span
            >
            <button
              class="clear-filters"
              on:click={() => {
                activeMetaStoryFilter = null;
              }}
              aria-label={$_("landing.clear_all")}
            >
              {$_("landing.clear_all")}
            </button>
          </div>
        </div>
      {:else if topTags.length > 0}
        <div class="tag-filters">
          <span class="filter-label">{$_("landing.filter_by_role")}</span>
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
          {#if activeTags.size > 0}
            <button
              class="clear-filters"
              on:click={() => {
                activeTags = new Set();
              }}
              aria-label={$_("landing.clear_all")}
            >
              {$_("landing.clear_all")}
            </button>
          {/if}
        </div>
      {/if}
    </div>
  </div>

  <div class="map-section" class:map-active={showMap}>
    <div class="map-toggle-container">
      <button
        class="map-toggle-button"
        class:active={showMap}
        on:click={() => (showMap = !showMap)}
        aria-label={showMap ? $_("landing.hide_map") : $_("landing.show_map")}
        aria-expanded={showMap}
        aria-controls="event-map-panel"
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path
            d="M15 19l-6-2.11V5l6 2.11M20.5 3c-.17 0-.34.03-.5.09L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5.17 0 .34-.03.5-.09L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5z"
          />
        </svg>
        <span>{showMap ? $_("landing.hide_map") : $_("landing.show_map")}</span>
      </button>
    </div>

    {#if showMap}
      <div
        id="event-map-panel"
        class="landing-map-wrapper"
        transition:slide={{ duration: 300 }}
      >
        {#await import("./LandingMap.svelte") then { default: LandingMap }}
          <LandingMap
            {filteredEntries}
            {getStyle}
            onNavigate={(detail) => {
              const lang = $currentLanguage;
              push(
                `/${lang}/story/${detail.personId}?event=${detail.eventIndex}`
              );
            }}
          />
        {/await}
      </div>
    {/if}
  </div>

  <div class="results-summary" role="status" aria-live="polite">
    {resultCountText}
  </div>

  <div class="landing-grid">
    {#if filteredEntries.length > 0}
      {#each filteredEntries as entry (entry.id)}
        {@const style = entry.style ?? getStyle(entry.id)}
        {@const lifespan = formatLifespan(entry)}
        {@const anniversary = getAnniversary(entry)}
        <button
          class="person-card"
          style={cardStyleVars(style)}
          on:click={() => handleSelect(entry.id)}
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
                {$_("landing.anniversary_today")}
              {:else if anniversary.daysUntil === 1}
                {$_("landing.anniversary_tomorrow")}
              {:else}
                {$_("landing.anniversary_in_days", {
                  days: anniversary.daysUntil,
                })}
              {/if}
              · {$_("landing.anniversary_years", { years: anniversary.years })}
            </span>
          {:else if isNewEntry(entry)}
            <span class="new-badge">{$_("landing.new_label")}</span>
          {/if}
          <figure class="person-thumb">
            {#if entry?.portrait}
              <img
                src={getThumbnailUrl(entry.portrait, 200)}
                srcset={`${getThumbnailUrl(entry.portrait, 200)} 1x, ${getThumbnailUrl(entry.portrait, 400)} 2x`}
                alt={loadedImages.has(entry.id)
                  ? (entry.portrait.alt ??
                    `Portrait of ${displayName(entry.name)}`)
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
                  <span class="meta-roles">
                    <SeparatedList
                      items={entry.primaryRoles}
                      styleConfig={style}
                    />
                  </span>
                </p>
              {/if}
            </div>
            {#if entry.tagline}
              <p class="card-tagline">{entry.tagline}</p>
            {/if}
            <span class="card-cta" aria-hidden="true"
              >{$_("landing.view_story")}</span
            >
          </div>
        </button>
      {/each}
    {:else if entries.length === 0}
      <p class="landing-empty">
        {$_("landing.empty_message")}
      </p>
    {:else}
      <div class="landing-empty">
        <span>{$_("landing.no_matches")}</span>
        <button class="clear-filters" on:click={clearFilters}>
          {$_("landing.clear_all")}
        </button>
      </div>
    {/if}
  </div>
</section>

<AIDisclaimerModal show={showExplanation} onClose={closeExplanation} />

<style>
  .landing {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    padding: 1rem 1.5rem 4rem;
    position: relative;
  }

  .skip-link {
    position: absolute;
    top: 0.5rem;
    left: 0.5rem;
    z-index: 300;
    padding: 0.6rem 0.85rem;
    border: 2px solid #38bdf8;
    border-radius: 0.4rem;
    background: #0f172a;
    color: #f8fafc;
    font: inherit;
    font-weight: 700;
    transform: translateY(-200%);
    transition: transform 0.15s ease;
  }

  .skip-link:focus {
    transform: translateY(0);
  }

  /* Sticky header group - wrapper for synchronized fade transition */
  .sticky-header-group {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 150;
    pointer-events: none;
  }

  .sticky-header-group > * {
    pointer-events: auto;
  }

  /* Sticky header - consistent with MetaStoryView */
  .landing-sticky-header {
    padding: 0.5rem 1rem;
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    background:
      linear-gradient(
        180deg,
        rgba(255, 255, 255, 0.03) 0%,
        rgba(0, 0, 0, 0.28) 100%
      ),
      rgba(15, 23, 42, 0.58);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid rgba(148, 163, 184, 0.16);
  }

  .sticky-ai-button {
    position: absolute;
    top: calc(var(--landing-sticky-header-height, 2.5rem) - 0.35rem);
    left: -0.25rem;
    z-index: -1; /* Below sticky header */
  }

  .sticky-center {
    flex: 1 1 auto;
    display: flex;
    justify-content: flex-start;
    min-width: 0;
  }

  .sticky-title {
    font-size: 0.85rem;
    font-weight: 700;
    color: #e2e8f0;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sticky-right {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  .language-selector.sticky {
    height: 1.85rem;
    padding: 0.35rem 0.5rem;
    font-size: 0.75rem;
    background: rgba(15, 23, 42, 0.6);
    border-color: rgba(148, 163, 184, 0.25);
  }

  @media (min-width: 768px) {
    .landing-sticky-header {
      padding: 0.5rem 2rem;
    }

    .sticky-title {
      font-size: 0.9rem;
    }

    .language-selector.sticky {
      height: 2rem;
      padding: 0.4rem 0.6rem;
      font-size: 0.8rem;
    }
  }

  .top-controls {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-bottom: 0;
    justify-content: space-between;
  }

  .top-controls-right {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .language-selector {
    height: 2.25rem;
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

  .header-container {
    display: flex;
    flex-direction: column;
    gap: 2rem;
  }

  /* Make carousel full-width on mobile */
  .header-container > :global(.meta-story-carousel) {
    margin-left: -1.5rem;
    margin-right: -1.5rem;
    width: calc(100% + 3rem);
  }

  @media (min-width: 768px) {
    .header-container > :global(.meta-story-carousel) {
      margin-left: 0;
      margin-right: 0;
      width: 100%;
    }
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
    overflow-wrap: anywhere;
    hyphens: auto;
  }

  .landing-hero p {
    margin: 0;
    font-size: 1rem;
    color: #cbd5f5;
  }

  .landing-hero .hero-intro {
    color: #cbd5e1;
    font-size: 1.05rem;
    max-width: 58ch;
  }

  .map-section {
    display: flex;
    flex-direction: column;
  }

  .map-section.map-active {
    margin-bottom: 0.5rem;
  }

  .map-toggle-container {
    display: flex;
    justify-content: flex-end;
  }

  .map-toggle-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.25rem;
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 0.5rem;
    color: #cbd5e1;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .map-toggle-button:hover {
    background: rgba(15, 23, 42, 0.95);
    border-color: rgba(56, 189, 248, 0.4);
    color: #38bdf8;
  }

  .map-toggle-button.active {
    background: rgba(15, 23, 42, 0.9);
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-bottom: none;
    border-bottom-left-radius: 0;
    border-bottom-right-radius: 0;
    color: #cbd5e1;
    position: relative;
    z-index: 2;
  }

  .map-toggle-button svg {
    flex-shrink: 0;
  }

  .landing-map-wrapper {
    width: calc(100% + 3rem);
    height: 400px;
    overflow: hidden;
    border: 1px solid rgba(148, 163, 184, 0.2);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
    margin-left: -1.5rem;
    margin-right: -1.5rem;
    border-radius: 0;
    border-left: none;
    border-right: none;
  }

  @media (min-width: 768px) {
    .landing-map-wrapper {
      margin-left: 0;
      margin-right: 0;
      width: 100%;
      height: 550px;
      border-radius: 1rem;
      border-top-right-radius: 0;
      border-left: 1px solid rgba(148, 163, 184, 0.2);
      border-right: 1px solid rgba(148, 163, 184, 0.2);
      border-top: none;
    }
  }

  .landing-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 1.5rem;
    grid-auto-rows: 1fr;
  }

  /* Full-width cards only in true single column mode */
  @media (max-width: 580px) {
    .landing-grid {
      gap: 0;
      margin-left: -1.5rem;
      margin-right: -1.5rem;
      width: calc(100% + 3rem);
    }
  }

  .results-summary {
    margin-top: -0.25rem;
    color: #cbd5e1;
    font-size: 0.95rem;
    font-weight: 600;
  }

  .landing-empty {
    margin: 0;
    font-size: 1rem;
    color: #94a3b8;
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .person-card {
    position: relative;
    display: grid;
    grid-template-columns: 100px 1fr;
    align-items: stretch;
    gap: 1.5rem;
    padding: 1.25rem 0.75rem 1.25rem 1rem;
    border-radius: 1rem;
    background-color: var(--card-bg, rgba(15, 23, 42, 0.94));
    border: 1px solid rgba(148, 163, 184, 0.18);
    box-shadow: 0 14px 32px rgba(15, 23, 42, 0.32);
    transition:
      transform 0.22s ease,
      border-color 0.22s ease,
      box-shadow 0.22s ease;
    min-height: 0;
    cursor: pointer;
    text-align: left;
    width: 100%;
    font-family: inherit;
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
    background-color: var(--card-primary, #38bdf8);
    background-image: var(--card-pattern-image, none);
    background-size: var(--card-pattern-size, 400px);
    background-repeat: repeat;
    background-position: calc(var(--card-pattern-size, 400px) / -2) calc(
        var(--card-pattern-size, 400px) / -2
      );
    background-blend-mode: multiply;
    opacity: var(--card-pattern-opacity, 1);
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
    margin: -0.5rem 0 -0.5rem -0.25rem;
    width: 120px;
    height: 180px; /* 2:3 aspect ratio (120 * 3/2 = 180) */
    border-radius: 0.9rem;
    overflow: hidden;
    background: transparent;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    z-index: 1;
    mix-blend-mode: lighten;
  }

  .person-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: top;
    display: block;
    mix-blend-mode: lighten;
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
    background:
      radial-gradient(
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

  .card-meta .meta-years {
    color: var(--card-secondary, rgba(148, 163, 184, 0.85));
    font-weight: 500;
  }

  .card-meta .meta-roles {
    color: var(--card-secondary, rgba(148, 163, 184, 0.85));
    text-transform: uppercase;
    font-size: 0.7rem;
  }

  .card-tagline {
    margin: 0;
    font-size: 1rem;
    color: rgba(203, 213, 225, 0.95);
    line-height: 1.4;
    font-weight: 500;
    font-style: italic;
    font-family: var(--card-body-font, Inter, sans-serif);
  }

  .card-cta {
    margin-top: auto;
    align-self: flex-start;
    color: #ffffff;
    font-size: 0.82rem;
    font-weight: 800;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    border-bottom: 2px solid var(--card-secondary, #38bdf8);
  }

  .person-card:hover .card-cta,
  .person-card:focus-visible .card-cta {
    color: var(--card-secondary, #bae6fd);
  }

  .person-card:focus-visible {
    outline: 3px solid var(--card-secondary, #38bdf8);
    outline-offset: 3px;
  }

  .eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.75rem;
    color: var(--card-secondary, rgba(56, 189, 248, 0.9));
    margin: 0;
  }

  .filters-section {
    display: flex;
    flex-direction: column;
    gap: 0.625rem;
  }

  .filters-right {
    display: flex;
    flex-direction: column;
    gap: 0.625rem;
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
    left: 0.75rem;
    color: #94a3b8;
    pointer-events: none;
  }

  .search-input {
    width: 100%;
    padding: 0.5rem 0.75rem 0.5rem 2.25rem;
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
    right: 0.4rem;
    padding: 0.3rem;
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
    flex-wrap: wrap;
    align-items: center;
    gap: 0.4rem;
  }

  .tag-filters-header {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    min-height: 1.8rem;
  }

  .filter-label {
    font-size: 0.8rem;
    font-weight: 500;
    color: #cbd5e1;
    flex-shrink: 0;
  }

  .clear-filters {
    padding: 0.25rem 0.55rem;
    border-radius: 0.35rem;
    background: rgba(148, 163, 184, 0.12);
    border: 1px solid rgba(148, 163, 184, 0.25);
    color: #94a3b8;
    font-size: 0.7rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .clear-filters:hover {
    background: rgba(148, 163, 184, 0.18);
    border-color: rgba(148, 163, 184, 0.4);
    color: #cbd5e1;
  }

  .tag-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.3rem 0.55rem;
    border-radius: 0.375rem;
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
    min-width: 1.05rem;
    height: 1.05rem;
    padding: 0 0.25rem;
    border-radius: 0.28rem;
    background: rgba(148, 163, 184, 0.2);
    font-size: 0.68rem;
    font-weight: 600;
    color: #cbd5e1;
  }

  .tag-chip.active .tag-count {
    background: rgba(56, 189, 248, 0.3);
    color: #e0f2fe;
  }

  @media (max-width: 580px) {
    .person-card {
      border-radius: 0;
      border-left: none;
      border-right: none;
    }
  }

  @media (max-width: 480px) {
    .person-card {
      grid-template-columns: 70px 1fr;
      gap: 1.25rem;
      padding: 1.1rem 0.6rem 1.1rem 1.2rem;
    }

    .person-thumb {
      margin: -0.5rem 0 -0.5rem -0.4rem;
      width: 90px;
      height: 135px; /* 2:3 aspect ratio (90 * 3/2 = 135) */
    }
  }

  @media (min-width: 768px) {
    .landing {
      padding: 2.5rem 3rem 5rem;
      gap: 1.5rem;
    }

    .header-container {
      display: grid;
      grid-template-columns: 1fr 2fr;
      gap: 3rem;
      align-items: start;
      margin-bottom: 1rem;
    }

    .landing-hero {
      max-width: none;
    }

    .landing-hero h1 {
      font-size: 2.6rem;
    }

    .filters-section {
      display: grid;
      grid-template-columns: minmax(13rem, 16rem) minmax(0, 1fr);
      gap: 0.75rem;
      align-items: flex-start;
    }

    .search-box {
      max-width: none;
    }

    .filters-right {
      flex: 1;
      min-width: 0;
    }

    .landing-grid {
      gap: 2rem;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    }

    .person-card {
      padding: 1.5rem 1rem 1.5rem 1.75rem;
      grid-template-columns: 92px 1fr;
      gap: 1.75rem;
    }

    .person-thumb {
      margin: -0.75rem 0 -0.75rem -0.25rem;
      width: 130px;
      height: 195px; /* 2:3 aspect ratio (130 * 3/2 = 195) */
    }

    .person-card h2 {
      font-size: 1.3rem;
    }
  }
</style>
