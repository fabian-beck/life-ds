<script>
  import { onMount } from "svelte";
  import { push, replace } from "svelte-spa-router";
  import { location, querystring } from "./stores/router.js";
  import Landing from "./components/Landing.svelte";
  import StoryView from "./components/StoryView.svelte";
  import MetaStoryView from "./components/MetaStoryView.svelte";
  import { currentLanguage, _ } from "./stores/language";
  // Side-effect import: the store's subscription applies the persisted
  // `html.high-contrast` class (see app.css) on every route, including
  // deep-linked story pages that never render the toggle button itself.
  import "./stores/contrast.js";
  import {
    queryParams,
    buildUrlWithParams,
    landingFilterQuery,
    navigationContext,
  } from "./stores/queryParams";
  import { restoreFocusTrigger } from "./stores/returnFocus.js";
  import {
    makeLocalizedLoader,
    mergeLocalized,
  } from "./utils/localizedData.js";
  import { displayName } from "./utils/helpers.js";
  import {
    filterVisible,
    isHidden,
    withHiddenFrom,
  } from "./utils/visibility.js";
  import { showHidden } from "./stores/visibility.js";
  import { parseHexColor } from "./utils/story/color.js";
  import { evaluationMode } from "./evaluation/log.js";
  import { participant, setParticipant } from "./evaluation/participant.js";

  // Initial registry (will be replaced with language-specific version)
  let registry = { people: [] };
  let englishRegistry = { people: [] }; // Always keep English registry for carousel
  let metaStories = [];

  // The style records for every person in the corpus, normalized once. They are
  // fetched rather than imported because the file is the one thing on the eager
  // path whose size is a function of how many lives the project has: roughly
  // 2 kB per person, and it only ever grows. Consumers see an empty map on the
  // first tick and the default style with it, which is what defaultStyle is for.
  let personStyles = {};

  async function loadPersonStyles() {
    try {
      const module = await import("../data/person_styles.json");
      personStyles = normalizeStyleRegistry(module.default);
    } catch (error) {
      console.warn("Failed to load person styles:", error);
      personStyles = {};
    }
  }

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
          // The hidden flag is read from the English entries, which the
          // localized ones replace whole (see utils/visibility.js).
          merged = {
            ...merged,
            people: withHiddenFrom(
              mergeLocalized(merged.people, localizedModule.default?.people),
              englishModule.default?.people
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
      const englishMetaStories = registryModule.default?.meta_stories || [];
      let metaStoryRegistry = englishMetaStories;
      if (language !== "en") {
        try {
          const localizedModule = await import(
            `../data/meta_stories_${language}.json`
          );
          metaStoryRegistry = withHiddenFrom(
            mergeLocalized(
              metaStoryRegistry,
              localizedModule.default?.meta_stories
            ),
            englishMetaStories
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

  // The evaluation deployment: a gate before the first view, and the logger
  // once the reader has a name. Both modules are loaded only when this build is
  // the evaluation one; everywhere else the condition is a constant, the
  // imports never run, and the ordinary site carries neither.
  let EvaluationGate = null;
  onMount(() => {
    // The literal comparison, not the exported constant: Vite substitutes the
    // variable at build time, so the branch folds away and the two chunks
    // behind these imports are not even emitted for the ordinary site.
    if (import.meta.env.VITE_EVALUATION_MODE !== "1") return undefined;
    import("./evaluation/EvaluationGate.svelte").then((module) => {
      EvaluationGate = module.default;
    });
    let stopLogging = null;
    let activeParticipant = null;
    const unsubscribe = participant.subscribe((id) => {
      activeParticipant = id;
      if (stopLogging) {
        stopLogging();
        stopLogging = null;
      }
      if (!id) return;
      import("./evaluation/logger.js").then((module) => {
        // The reader may have changed the id again while the chunk loaded.
        if (activeParticipant !== id || stopLogging) return;
        stopLogging = module.startLogging(id);
      });
    });
    return () => {
      unsubscribe();
      if (stopLogging) stopLogging();
    };
  });

  // Reload registry and meta stories when language changes
  onMount(() => {
    loadPersonStyles();
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
    ],
    {
      import: "default",
    }
  );

  const egoNetworkModules = import.meta.glob(
    [
      "../data/people/*/ego_network.json",
      "../data/people/*/de/ego_network.json",
    ],
    {
      import: "default",
    }
  );

  const metaStoryDetailModules = import.meta.glob(
    ["../data/meta_stories/*.json", "../data/meta_stories/de/*.json"],
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

  function normalizeStyle(raw) {
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
    const normalized = normalizeStyle(defaultStyleBase) ?? {};
    return {
      primary: normalized.primary ?? defaultStyleBase.primary,
      secondary: normalized.secondary ?? defaultStyleBase.secondary,
      background: normalized.background ?? defaultStyleBase.background,
      backgroundRgb:
        normalized.backgroundRgb ??
        hexToRgb(defaultStyleBase.background) ??
        "15, 23, 42",
      backgroundPatternSvg:
        normalized.backgroundPatternSvg ??
        defaultStyleBase.background_pattern_svg,
      backgroundPatternDataUrl:
        normalized.backgroundPatternDataUrl ??
        svgToDataUrl(defaultStyleBase.background_pattern_svg),
      headingFont: normalized.headingFont ?? "Inter",
      bodyFont: normalized.bodyFont ?? "Inter",
    };
  })();

  function normalizeStyleRegistry(registry) {
    const rawStyles =
      registry && typeof registry === "object" ? registry.styles : null;
    if (!rawStyles || typeof rawStyles !== "object") {
      return {};
    }
    return Object.entries(rawStyles).reduce((accumulator, [key, value]) => {
      const normalized = normalizeStyle(value);
      if (normalized) {
        accumulator[key] = normalized;
      }
      return accumulator;
    }, {});
  }

  // Rebuilt when the records arrive, so everything derived from it — the
  // registry entries, the story's own palette, the landing cards — recomputes
  // then rather than keeping the default it was built with.
  $: styleFor = makeStyleFor(personStyles);

  function makeStyleFor(styles) {
    return (id) => styleForIn(styles, id);
  }

  function styleForIn(styles, id) {
    if (!id) {
      return { ...defaultStyle };
    }
    const override = styles[id];
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

  // The three localized documents, each addressed a little differently but
  // all following the one fallback rule (see utils/localizedData.js).
  const loadDataset = makeLocalizedLoader({
    modules: datasetModules,
    pathFor: (personId, language) =>
      language === "en"
        ? `../data/people/${personId}/life_events.json`
        : `../data/people/${personId}/${language}/life_events.json`,
    label: "Dataset",
  });

  const loadEgoNetwork = makeLocalizedLoader({
    modules: egoNetworkModules,
    pathFor: (personId, language) =>
      language === "en"
        ? `../data/people/${personId}/ego_network.json`
        : `../data/people/${personId}/${language}/ego_network.json`,
    label: "Network",
  });

  // A meta story id comes from a registry that promised the file exists, so
  // finding nothing is worth saying out loud; a person's missing network is not.
  const loadMetaStoryData = makeLocalizedLoader({
    modules: metaStoryDetailModules,
    pathFor: (metaStoryId, language) =>
      language === "en"
        ? `../data/meta_stories/${metaStoryId}.json`
        : `../data/meta_stories/${language}/${metaStoryId}.json`,
    label: "Meta story",
    warnWhenMissing: true,
  });

  // What the reader may see. The registries keep people and collections
  // marked hidden; a production build never shows them, and the development
  // server shows them until the deployment preview is switched on (see
  // stores/visibility.js). Every view reads these lists rather than the
  // registries, so a hidden person is absent from the landing grid, the
  // related-people cards, the collection cast, and the mentions alike.
  $: visibleRegistry = {
    ...registry,
    people: filterVisible(registry?.people, $showHidden),
  };
  $: visibleMetaStories = filterVisible(metaStories, $showHidden);

  // Build registry entries directly from registry data (no dataset loading needed)
  $: registryEntries = visibleRegistry.people.map((entry) => ({
    ...entry,
    style: styleFor(entry.id),
  }));

  // Build English registry entries for carousel (portraits always from English data)
  $: englishRegistryEntries = filterVisible(
    englishRegistry?.people,
    $showHidden
  ).map((entry) => ({
    ...entry,
    style: styleFor(entry.id),
  }));

  function entrySummary(entry) {
    if (!entry?.id) return "";
    return entry.summary ?? "";
  }

  // Extract person ID and language from current route (slide is now a query param)
  // Updated regex patterns to support optional language prefix: /en/story/... or /story/...
  $: currentPath = $location;
  $: storyMatch = currentPath.match(/^\/(?:([a-z]{2})\/)?story\/([^/]+)/);
  $: legacyExhibitionMatch = currentPath.match(
    /^\/(?:([a-z]{2})\/)?exhibition\/([^/]+)/
  );
  $: metaMatch = currentPath.match(/^\/(?:([a-z]{2})\/)?meta\/([^/]+)/);
  // Also match landing page with language prefix: /en, /de, etc.
  $: landingMatch = currentPath.match(/^\/([a-z]{2})(?:\/|$)/);
  $: langFromUrl =
    storyMatch?.[1] ||
    legacyExhibitionMatch?.[1] ||
    metaMatch?.[1] ||
    landingMatch?.[1] ||
    null;
  $: personId = storyMatch ? decodeURIComponent(storyMatch[2]) : null;
  $: metaStoryId = metaMatch ? decodeURIComponent(metaMatch[2]) : null;
  $: slideParam = $queryParams.slide;
  $: eventParam = $queryParams.event;

  // Sync language from URL to store (URL takes precedence for shareable intent)
  $: if (langFromUrl && langFromUrl !== $currentLanguage) {
    currentLanguage.set(langFromUrl);
  }
  // The removed exhibition surface has a direct story equivalent, so keep
  // existing bookmarks useful without loading any exhibition-only code.
  $: if (legacyExhibitionMatch) {
    const legacyLanguage = legacyExhibitionMatch[1] || $currentLanguage;
    const legacyPersonId = decodeURIComponent(legacyExhibitionMatch[2]);
    replace(`/${legacyLanguage}/story/${encodeURIComponent(legacyPersonId)}`);
  }

  // Redirect to language-prefixed URL if accessing any page without language
  $: if (!langFromUrl && currentPath !== "/" && !legacyExhibitionMatch) {
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

  // A hidden story is not there for a reader who may not see hidden entries:
  // its route goes home the way an unknown id does. The registries decide,
  // so the check waits for them and passes an id they do not know yet.
  $: routeHidden =
    !$showHidden &&
    ((personId &&
      isHidden(englishRegistry?.people?.find((e) => e.id === personId))) ||
      (metaStoryId &&
        isHidden(metaStories.find((story) => story.id === metaStoryId))));
  $: if (routeHidden) {
    replace(`/${$currentLanguage}`);
  }

  // Reactive data loading - load when personId OR language changes
  let dataset = null;
  let egoNetwork = null;
  let loadedPersonId = null;
  let loadedDatasetLanguage = null;
  let metaStoryData = null;
  let dataLoading = false;
  let loadingStage = null; // Track which part is loading: 'initial', 'dataset', 'network', null

  // Clear whatever person story is on screen. Written out four times before —
  // when a person starts loading, when that load fails, when the route leaves
  // a person, and when a meta story takes over the view.
  function resetPersonState() {
    dataset = null;
    egoNetwork = null;
    loadedPersonId = null;
    loadedDatasetLanguage = null;
  }

  // Shared across person and meta story loading: navigating quickly between
  // people (or between a person and a meta story) leaves earlier loads in
  // flight, and without this guard the last one to *resolve* would win and
  // overwrite the data of the story actually being viewed.
  let dataLoadGeneration = 0;

  $: if (personId && $currentLanguage && !routeHidden) {
    const generation = ++dataLoadGeneration;
    const requestedPersonId = personId;
    const requestedLanguage = $currentLanguage;
    dataLoading = true;
    loadingStage = "initial";
    resetPersonState();

    // Load dataset first (includes portrait and events)
    loadingStage = "dataset";
    loadDataset(requestedPersonId, requestedLanguage)
      .then((datasetResult) => {
        if (generation !== dataLoadGeneration) return null;
        dataset = datasetResult;
        loadedPersonId = requestedPersonId;
        loadedDatasetLanguage = requestedLanguage;
        loadingStage = "network";
        // Load network data after dataset
        return loadEgoNetwork(requestedPersonId, requestedLanguage);
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
        resetPersonState();
        dataLoading = false;
        loadingStage = null;
      });
  } else if (!personId) {
    dataLoadGeneration += 1;
    resetPersonState();
    dataLoading = false;
    loadingStage = null;
  }

  // Reactive meta story loading - load when metaStoryId OR language changes
  $: if (metaStoryId && $currentLanguage && !routeHidden) {
    const generation = ++dataLoadGeneration;
    dataLoading = true;
    metaStoryData = null;
    resetPersonState();

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

  // Reactive page title: name whichever story is open — a person or a
  // collection — and take the site name from the active language, since the
  // tab and the bookmark are the one place a title is read.
  $: currentTitlePerson = dataset?.person?.name
    ? displayName(dataset.person.name)
    : null;
  $: currentTitleStory =
    currentTitlePerson || metaStoryData?.meta_story?.title || null;
  $: document.title = currentTitleStory
    ? `${$_("app.title")} · ${currentTitleStory}`
    : $_("app.title");

  // Redirect to home if trying to view a non-existent story after loading completes.
  $: if (storyMatch && !dataset && personId && !dataLoading) {
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

  // The landing filters the reader arrived with, carried through the story
  // route the same way. On the landing itself they are the live query string;
  // once inside a story or collection they travel as `from_landing`.
  $: fromLanding =
    !storyMatch && !metaMatch
      ? landingFilterQuery($querystring)
      : $queryParams.from_landing;

  function landingUrl(filterQuery) {
    const basePath = `/${$currentLanguage}`;
    return filterQuery ? `${basePath}?${filterQuery}` : basePath;
  }

  function handleSelectPerson(event) {
    const id = event.detail;
    if (id) {
      const basePath = `/${$currentLanguage}/story/${encodeURIComponent(id)}`;
      push(buildUrlWithParams(basePath, { from_landing: fromLanding }));
    }
  }

  function handleCloseStory() {
    if (fromMetaStoryId) {
      const basePath = `/${$currentLanguage}/meta/${fromMetaStoryId}`;
      replace(buildUrlWithParams(basePath, { from_landing: fromLanding }));
    } else {
      replace(landingUrl(fromLanding));
      // The card that opened the story is gone with the route; put the reader
      // back on it rather than dropping focus to the top of the document.
      restoreFocusTrigger("[data-landing-heading]");
    }
  }

  function handleSlideChange(event) {
    // Ignore transient scroll notifications while a language change has
    // unloaded the current dataset. The route already carries the requested
    // slide and remains the source of truth until the replacement data loads.
    if (
      dataLoading ||
      !dataset ||
      loadedPersonId !== personId ||
      loadedDatasetLanguage !== langFromUrl
    )
      return;

    const slideIndex = event.detail;

    if (personId && slideIndex !== null && slideIndex !== undefined) {
      // Base path without slide (slide is now a query param)
      const basePath = `/${$currentLanguage}/story/${encodeURIComponent(personId)}`;

      // Build URL with all query params (slide, timeline, network, context)
      const newPath = buildUrlWithParams(basePath, {
        slide: slideIndex,
        timeline: $queryParams.timeline,
        network: $queryParams.network,
        ...navigationContext($queryParams),
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
      {personStyles}
      personsRegistry={visibleRegistry.people}
      currentLanguage={$currentLanguage}
      isLoading={dataLoading}
    />
  {:else if storyMatch}
    <StoryView
      {dataset}
      {egoNetwork}
      personsRegistry={visibleRegistry}
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
      metaStories={visibleMetaStories}
      getSummary={entrySummary}
      getStyle={styleFor}
      onSelectPerson={handleSelectPerson}
    />
  {/if}
</div>

{#if evaluationMode && EvaluationGate && !$participant}
  <svelte:component this={EvaluationGate} onSubmit={setParticipant} />
{/if}

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
