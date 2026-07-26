<script>
  import { onMount } from "svelte";
  import { push, replace } from "svelte-spa-router";
  import { location } from "./stores/router.js";
  import Landing from "./components/Landing.svelte";
  import StoryView from "./components/StoryView.svelte";
  import ExhibitionView from "./components/ExhibitionView.svelte";
  import MetaStoryView from "./components/MetaStoryView.svelte";
  import { currentLanguage, loadTranslations, _ } from "./stores/language";
  // Side-effect import: the store's subscription applies the persisted
  // `html.high-contrast` class (see app.css) on every route, including
  // deep-linked story pages that never render the toggle button itself.
  import "./stores/contrast.js";
  import { queryParams, buildUrlWithParams } from "./stores/queryParams";
  import styleRegistry from "../data/person_styles.json";
  import { displayName } from "./utils/helpers.js";
  import { parseHexColor } from "./utils/storyHelpers.js";

  // Reload translations when language changes
  onMount(() => {
    const unsubscribe = currentLanguage.subscribe((lang) => {
      loadTranslations(lang);
    });
    return unsubscribe;
  });

  // Initial registry (will be replaced with language-specific version)
  let registry = { people: [] };
  let englishRegistry = { people: [] }; // Always keep English registry for carousel
  let metaStories = [];

  // Load English registry (for carousel portraits)
  async function loadEnglishRegistry() {
    try {
      const module = await import("../data/persons.json");
      englishRegistry = module.default;
    } catch (error) {
      console.warn("Failed to load English registry:", error);
      englishRegistry = { people: [] };
    }
  }

  // Load language-specific registry. The English registry is always the
  // reference: localized entries are merged over it per person, so people
  // without a translation still appear (with English text) and the person
  // list is identical in every language. The generation counter guards
  // against rapid language switches: only the most recent request may write
  // the result.
  let registryLoadGeneration = 0;
  async function loadRegistry(language) {
    const generation = ++registryLoadGeneration;
    try {
      const englishModule = await import("../data/persons.json");
      let merged = englishModule.default;
      if (language !== "en") {
        try {
          const localizedModule = await import(
            `../data/persons_${language}.json`
          );
          const localizedById = new Map(
            (localizedModule.default?.people ?? []).map((person) => [
              person.id,
              person,
            ])
          );
          merged = {
            ...merged,
            people: (merged.people ?? []).map(
              (person) => localizedById.get(person.id) ?? person
            ),
          };
        } catch (error) {
          console.warn(
            `No registry for ${language}, falling back to English:`,
            error
          );
        }
      }
      if (generation !== registryLoadGeneration) return;
      registry = merged;
    } catch (error) {
      console.warn(`Failed to load registry for ${language}:`, error);
    }
  }

  // Load meta stories with detailed data. Like the persons registry, the
  // English meta story registry is the reference and localized entries are
  // merged over it per story. The generation counter guards against rapid
  // language switches.
  let metaStoriesLoadGeneration = 0;
  async function loadMetaStories(language = "en") {
    const generation = ++metaStoriesLoadGeneration;
    try {
      const registryModule = await import("../data/meta_stories.json");
      let metaStoryRegistry = registryModule.default?.meta_stories || [];
      if (language !== "en") {
        try {
          const localizedModule = await import(
            `../data/meta_stories_${language}.json`
          );
          const localizedById = new Map(
            (localizedModule.default?.meta_stories ?? []).map((story) => [
              story.id,
              story,
            ])
          );
          metaStoryRegistry = metaStoryRegistry.map(
            (story) => localizedById.get(story.id) ?? story
          );
        } catch {
          // No localized meta story registry yet — English fallback
        }
      }

      // Load detailed data for each meta story
      const detailedStories = await Promise.all(
        metaStoryRegistry.map(async (story) => {
          try {
            const detailData = await loadMetaStoryData(story.id, language);
            return {
              ...story,
              person_ids: detailData?.meta_story?.person_ids || [],
            };
          } catch (error) {
            console.warn(
              `Failed to load details for meta story ${story.id}:`,
              error
            );
            return story;
          }
        })
      );

      if (generation !== metaStoriesLoadGeneration) return;
      metaStories = detailedStories;
    } catch (error) {
      console.warn("Failed to load meta stories:", error);
      if (generation !== metaStoriesLoadGeneration) return;
      metaStories = [];
    }
  }

  // Reload registry and meta stories when language changes
  onMount(() => {
    loadEnglishRegistry(); // Load English registry once for carousel
    const unsubscribe = currentLanguage.subscribe((lang) => {
      loadRegistry(lang);
      loadMetaStories(lang);
    });
    return unsubscribe;
  });

  // Lazy loading - include both base and language-specific paths
  const datasetModules = import.meta.glob(
    [
      "../data/people/*/life_events.json",
      "../data/people/*/de/life_events.json",
      "../data/people/*/fr/life_events.json",
    ],
    {
      import: "default",
    }
  );

  const egoNetworkModules = import.meta.glob(
    [
      "../data/people/*/ego_network.json",
      "../data/people/*/de/ego_network.json",
      "../data/people/*/fr/ego_network.json",
    ],
    {
      import: "default",
    }
  );

  const metaStoryDetailModules = import.meta.glob(
    [
      "../data/meta_stories/*.json",
      "../data/meta_stories/de/*.json",
      "../data/meta_stories/fr/*.json",
    ],
    {
      import: "default",
    }
  );

  function isHexColor(value) {
    return !!parseHexColor(value);
  }

  function hexToRgb(value) {
    const parsed = parseHexColor(value);
    return parsed ? `${parsed.r}, ${parsed.g}, ${parsed.b}` : null;
  }

  function svgToDataUrl(svg) {
    if (typeof svg !== "string") return null;
    const trimmed = svg.trim();
    if (!trimmed.startsWith("<svg")) {
      return null;
    }
    const encoded = encodeURIComponent(trimmed).replace(/%0A/g, "");
    return `data:image/svg+xml,${encoded}`;
  }

  function normaliseStyle(raw) {
    if (!raw || typeof raw !== "object") return null;
    const result = {};
    if (isHexColor(raw.primary)) {
      result.primary = raw.primary.trim().toUpperCase();
    }
    if (isHexColor(raw.secondary)) {
      result.secondary = raw.secondary.trim().toUpperCase();
    }
    if (isHexColor(raw.background)) {
      result.background = raw.background.trim().toUpperCase();
      const rgb = hexToRgb(result.background);
      if (rgb) {
        result.backgroundRgb = rgb;
      }
    }
    if (typeof raw.background_pattern_svg === "string") {
      const svg = raw.background_pattern_svg.trim();
      if (svg.includes("<svg")) {
        result.backgroundPatternSvg = svg;
        const dataUrl = svgToDataUrl(svg);
        if (dataUrl) {
          result.backgroundPatternDataUrl = dataUrl;
        }
      }
    }
    if (typeof raw.separator_glyph_svg === "string") {
      const svg = raw.separator_glyph_svg.trim();
      if (svg.includes("<svg")) {
        result.separatorGlyphSvg = svg;
        const dataUrl = svgToDataUrl(svg);
        if (dataUrl) {
          result.separatorGlyphDataUrl = dataUrl;
        }
      }
    }
    if (typeof raw.heading_font === "string" && raw.heading_font.trim()) {
      result.headingFont = raw.heading_font.trim();
    }
    if (typeof raw.body_font === "string" && raw.body_font.trim()) {
      result.bodyFont = raw.body_font.trim();
    }
    return Object.keys(result).length > 0 ? result : null;
  }

  const defaultStyleBase = {
    primary: "#38BDF8",
    secondary: "#FACC15",
    background: "#0F172A",
    background_pattern_svg:
      '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160"><rect width="160" height="160" fill="#000000"/><path fill="#FFFFFF" d="M0 0h20v20H0zM40 40h20v20H40zM80 0h20v20H80zM120 40h20v20h-20zM0 80h20v20H0zM80 80h20v20H80zM40 120h20v20H40zM120 120h20v20h-20z"/></svg>',
  };

  const defaultStyle = (() => {
    const normalised = normaliseStyle(defaultStyleBase) ?? {};
    return {
      primary: normalised.primary ?? defaultStyleBase.primary,
      secondary: normalised.secondary ?? defaultStyleBase.secondary,
      background: normalised.background ?? defaultStyleBase.background,
      backgroundRgb:
        normalised.backgroundRgb ??
        hexToRgb(defaultStyleBase.background) ??
        "15, 23, 42",
      backgroundPatternSvg:
        normalised.backgroundPatternSvg ??
        defaultStyleBase.background_pattern_svg,
      backgroundPatternDataUrl:
        normalised.backgroundPatternDataUrl ??
        svgToDataUrl(defaultStyleBase.background_pattern_svg),
      headingFont: normalised.headingFont ?? "Inter",
      bodyFont: normalised.bodyFont ?? "Inter",
    };
  })();

  const personStyles = (() => {
    const rawStyles =
      styleRegistry && typeof styleRegistry === "object"
        ? styleRegistry.styles
        : null;
    if (!rawStyles || typeof rawStyles !== "object") {
      return {};
    }
    return Object.entries(rawStyles).reduce((accumulator, [key, value]) => {
      const normalised = normaliseStyle(value);
      if (normalised) {
        accumulator[key] = normalised;
      }
      return accumulator;
    }, {});
  })();

  function styleFor(id) {
    if (!id) {
      return { ...defaultStyle };
    }
    const override = personStyles[id];
    if (!override) {
      return { ...defaultStyle };
    }
    return {
      ...defaultStyle,
      ...override,
      backgroundRgb: override.backgroundRgb ?? defaultStyle.backgroundRgb,
      backgroundPatternSvg:
        override.backgroundPatternSvg ?? defaultStyle.backgroundPatternSvg,
      backgroundPatternDataUrl:
        override.backgroundPatternDataUrl ??
        defaultStyle.backgroundPatternDataUrl,
      patternOpacity: override.patternOpacity ?? defaultStyle.patternOpacity,
      headingFont: override.headingFont ?? defaultStyle.headingFont,
      bodyFont: override.bodyFont ?? defaultStyle.bodyFont,
    };
  }

  // Helper to load data on-demand
  async function loadDataset(personId, language = "en") {
    // Try language-specific path first
    let path =
      language === "en"
        ? `../data/people/${personId}/life_events.json`
        : `../data/people/${personId}/${language}/life_events.json`;

    let loader = datasetModules[path];

    // Fallback to English if translation doesn't exist
    if (!loader && language !== "en") {
      console.warn(
        `Translation not found for ${personId} in ${language}, falling back to English`
      );
      path = `../data/people/${personId}/life_events.json`;
      loader = datasetModules[path];
    }

    if (!loader) return null;

    try {
      return await loader();
    } catch (error) {
      console.error(`Failed to load dataset for ${personId}:`, error);
      return null;
    }
  }

  async function loadEgoNetwork(personId, language = "en") {
    let path =
      language === "en"
        ? `../data/people/${personId}/ego_network.json`
        : `../data/people/${personId}/${language}/ego_network.json`;

    let loader = egoNetworkModules[path];

    // Fallback to English
    if (!loader && language !== "en") {
      console.warn(
        `Network translation not found for ${personId} in ${language}, falling back to English`
      );
      path = `../data/people/${personId}/ego_network.json`;
      loader = egoNetworkModules[path];
    }

    if (!loader) return null;

    try {
      return await loader();
    } catch (error) {
      console.error(`Failed to load ego network for ${personId}:`, error);
      return null;
    }
  }

  async function loadMetaStoryData(metaStoryId, language = "en") {
    let path =
      language === "en"
        ? `../data/meta_stories/${metaStoryId}.json`
        : `../data/meta_stories/${language}/${metaStoryId}.json`;

    let loader = metaStoryDetailModules[path];

    // Fallback to English if translation doesn't exist
    if (!loader && language !== "en") {
      console.warn(
        `Meta story translation not found for ${metaStoryId} in ${language}, falling back to English`
      );
      path = `../data/meta_stories/${metaStoryId}.json`;
      loader = metaStoryDetailModules[path];
    }

    if (!loader) {
      console.warn(`Meta story not found: ${metaStoryId}`);
      return null;
    }

    try {
      return await loader();
    } catch (error) {
      console.error(`Failed to load meta story ${metaStoryId}:`, error);
      return null;
    }
  }

  // Build registry entries directly from registry data (no dataset loading needed)
  $: registryEntries = (() => {
    if (!Array.isArray(registry?.people)) {
      return [];
    }
    return registry.people.map((entry) => ({
      ...entry,
      style: styleFor(entry.id),
    }));
  })();

  // Build English registry entries for carousel (portraits always from English data)
  $: englishRegistryEntries = (() => {
    if (!Array.isArray(englishRegistry?.people)) {
      return [];
    }
    return englishRegistry.people.map((entry) => ({
      ...entry,
      style: styleFor(entry.id),
    }));
  })();

  function entrySummary(entry) {
    if (!entry?.id) return "";
    return entry.summary ?? "";
  }

  // Extract person ID and language from current route (slide is now a query param)
  // Updated regex patterns to support optional language prefix: /en/story/... or /story/...
  $: currentPath = $location;
  $: storyMatch = currentPath.match(/^\/(?:([a-z]{2})\/)?story\/([^/]+)/);
  $: exhibitionMatch = currentPath.match(
    /^\/(?:([a-z]{2})\/)?exhibition\/([^/]+)/
  );
  $: metaMatch = currentPath.match(/^\/(?:([a-z]{2})\/)?meta\/([^/]+)/);
  // Also match landing page with language prefix: /en, /de, etc.
  $: landingMatch = currentPath.match(/^\/([a-z]{2})(?:\/|$)/);
  $: langFromUrl =
    storyMatch?.[1] ||
    exhibitionMatch?.[1] ||
    metaMatch?.[1] ||
    landingMatch?.[1] ||
    null;
  $: personId = storyMatch
    ? decodeURIComponent(storyMatch[2])
    : exhibitionMatch
      ? decodeURIComponent(exhibitionMatch[2])
      : null;
  $: metaStoryId = metaMatch ? decodeURIComponent(metaMatch[2]) : null;
  $: slideParam = $queryParams.slide;
  $: eventParam = $queryParams.event;

  // Sync language from URL to store (URL takes precedence for shareable intent)
  $: if (langFromUrl && langFromUrl !== $currentLanguage) {
    currentLanguage.set(langFromUrl);
  }

  // Redirect to language-prefixed URL if accessing any page without language
  $: if (!langFromUrl && currentPath !== "/") {
    // Don't redirect if we're already on a language-prefixed path
    if (!currentPath.startsWith(`/${$currentLanguage}`)) {
      const newPath = `/${$currentLanguage}${currentPath}`;
      replace(newPath);
    }
  }

  // Redirect root path to language-prefixed landing page
  $: if (currentPath === "/") {
    replace(`/${$currentLanguage}`);
  }

  // Reactive data loading - load when personId OR language changes
  let dataset = null;
  let egoNetwork = null;
  let metaStoryData = null;
  let dataLoading = false;
  let loadingStage = null; // Track which part is loading: 'initial', 'dataset', 'network', null

  // Shared across person and meta story loading: navigating quickly between
  // people (or between a person and a meta story) leaves earlier loads in
  // flight, and without this guard the last one to *resolve* would win and
  // overwrite the data of the story actually being viewed.
  let dataLoadGeneration = 0;

  $: if (personId && $currentLanguage) {
    const generation = ++dataLoadGeneration;
    dataLoading = true;
    loadingStage = "initial";
    dataset = null;
    egoNetwork = null;

    // Load dataset first (includes portrait and events)
    loadingStage = "dataset";
    loadDataset(personId, $currentLanguage)
      .then((datasetResult) => {
        if (generation !== dataLoadGeneration) return null;
        dataset = datasetResult;
        loadingStage = "network";
        // Load network data after dataset
        return loadEgoNetwork(personId, $currentLanguage);
      })
      .then((networkResult) => {
        if (generation !== dataLoadGeneration) return;
        egoNetwork = networkResult;
        dataLoading = false;
        loadingStage = null;
      })
      .catch((error) => {
        if (generation !== dataLoadGeneration) return;
        console.error("Failed to load data:", error);
        dataset = null;
        egoNetwork = null;
        dataLoading = false;
        loadingStage = null;
      });
  } else if (!personId) {
    dataLoadGeneration += 1;
    dataset = null;
    egoNetwork = null;
    dataLoading = false;
    loadingStage = null;
  }

  // Reactive meta story loading - load when metaStoryId OR language changes
  $: if (metaStoryId && $currentLanguage) {
    const generation = ++dataLoadGeneration;
    dataLoading = true;
    metaStoryData = null;
    dataset = null;
    egoNetwork = null;

    loadMetaStoryData(metaStoryId, $currentLanguage)
      .then((result) => {
        if (generation !== dataLoadGeneration) return;
        metaStoryData = result;
        dataLoading = false;
      })
      .catch((error) => {
        if (generation !== dataLoadGeneration) return;
        console.error("Failed to load meta story:", error);
        metaStoryData = null;
        dataLoading = false;
      });
  } else if (!metaStoryId && !personId) {
    metaStoryData = null;
  }

  // Reactive page title: use current person's name if available, else generic.
  $: currentTitlePerson = dataset?.person?.name
    ? displayName(dataset.person.name)
    : null;
  $: document.title = currentTitlePerson
    ? `Life Data Stories · ${currentTitlePerson}`
    : "Life Data Stories";

  // Redirect to home if trying to view non-existent story or exhibition (after loading completes)
  $: if (
    (storyMatch || exhibitionMatch) &&
    !dataset &&
    personId &&
    !dataLoading
  ) {
    push(`/${$currentLanguage}`);
  }

  // Replace invalid collection routes so a stale link cannot trap the visitor
  // on an empty page or remain in browser history.
  $: if (metaMatch && !metaStoryData && metaStoryId && !dataLoading) {
    replace(`/${$currentLanguage}`);
  }

  // Extract from_meta parameter to preserve meta story context
  // Use the queryParams store which is already reactive to URL changes
  $: fromMetaStoryId = $queryParams.from_meta;

  function handleSelectPerson(event) {
    const id = event.detail;
    if (id) {
      push(`/${$currentLanguage}/story/${encodeURIComponent(id)}`);
    }
  }

  function handleCloseStory() {
    if (fromMetaStoryId) {
      replace(`/${$currentLanguage}/meta/${fromMetaStoryId}`);
    } else {
      replace(`/${$currentLanguage}`);
    }
  }

  function handleSlideChange(event) {
    const slideIndex = event.detail;

    if (personId && slideIndex !== null && slideIndex !== undefined) {
      // Base path without slide (slide is now a query param)
      const basePath = `/${$currentLanguage}/story/${encodeURIComponent(personId)}`;

      // Build URL with all query params (slide, timeline, network, from_meta)
      const newPath = buildUrlWithParams(basePath, {
        slide: slideIndex,
        timeline: $queryParams.timeline,
        network: $queryParams.network,
        from_meta: $queryParams.from_meta, // Preserve meta story context
      });

      // Always use replace() - slide changes are presentation state,
      // not navigation history. This prevents the back button from
      // stepping through every slide change.
      replace(newPath);
    }
  }
</script>

<div class="shell">
  {#if metaMatch}
    <MetaStoryView
      {metaStoryData}
      personsRegistry={registry.people}
      currentLanguage={$currentLanguage}
      isLoading={dataLoading}
    />
  {:else if exhibitionMatch}
    <ExhibitionView
      {dataset}
      {egoNetwork}
      isLoading={dataLoading}
      styleConfig={styleFor(personId)}
    />
  {:else if storyMatch}
    <StoryView
      {dataset}
      {egoNetwork}
      personsRegistry={registry}
      personStylesRegistry={personStyles}
      isLoading={dataLoading}
      {loadingStage}
      activeIndex={slideParam ?? 0}
      targetEventIndex={eventParam}
      styleConfig={styleFor(personId)}
      onClose={handleCloseStory}
      onSlideChange={handleSlideChange}
    />
  {:else}
    <Landing
      entries={registryEntries}
      englishEntries={englishRegistryEntries}
      {metaStories}
      getSummary={entrySummary}
      getStyle={styleFor}
      onSelectPerson={handleSelectPerson}
    />
  {/if}
</div>

<style>
  :global(body) {
    overscroll-behavior: contain;
    padding-bottom: env(safe-area-inset-bottom);
  }

  :global(:root) {
    --header-height: 11.5rem;
  }

  .shell {
    min-height: 100vh;
    min-height: 100dvh;
    display: flex;
    flex-direction: column;
    color: #e2e8f0;
  }

  @media (min-width: 768px) {
    :global(:root) {
      --header-height: 9.5rem;
    }
  }
</style>
