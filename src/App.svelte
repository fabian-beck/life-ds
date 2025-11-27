<script>
  import { push, pop, replace, location } from "svelte-spa-router";
  import Landing from "./components/Landing.svelte";
  import StoryView from "./components/StoryView.svelte";
  import ExhibitionView from "./components/ExhibitionView.svelte";
  import registry from "../data/persons.json";
  import styleRegistry from "../data/person_styles.json";

  // Lazy loading - functions return promises
  const datasetModules = import.meta.glob("../data/people/*/life_events.json", {
    import: "default",
  });

  const egoNetworkModules = import.meta.glob(
    "../data/people/*/ego_network.json",
    {
      import: "default",
    }
  );

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function isHexColor(value) {
    return typeof value === "string" && /^#[0-9a-fA-F]{6}$/.test(value.trim());
  }

  function hexToRgb(value) {
    if (!isHexColor(value)) return null;
    const hex = value.trim().replace("#", "");
    const r = parseInt(hex.slice(0, 2), 16);
    const g = parseInt(hex.slice(2, 4), 16);
    const b = parseInt(hex.slice(4, 6), 16);
    if ([r, g, b].some((component) => Number.isNaN(component))) {
      return null;
    }
    return `${r}, ${g}, ${b}`;
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
  async function loadDataset(personId) {
    const path = `../data/people/${personId}/life_events.json`;
    const loader = datasetModules[path];
    if (!loader) return null;
    try {
      return await loader();
    } catch (error) {
      console.error(`Failed to load dataset for ${personId}:`, error);
      return null;
    }
  }

  async function loadEgoNetwork(personId) {
    const path = `../data/people/${personId}/ego_network.json`;
    const loader = egoNetworkModules[path];
    if (!loader) return null;
    try {
      return await loader();
    } catch (error) {
      console.error(`Failed to load ego network for ${personId}:`, error);
      return null;
    }
  }

  // Build registry entries directly from registry data (no dataset loading needed)
  const registryEntries = (() => {
    if (!Array.isArray(registry?.people)) {
      return [];
    }
    return registry.people.map((entry) => ({
      ...entry,
      style: styleFor(entry.id),
    }));
  })();

  function entrySummary(entry) {
    if (!entry?.id) return "";
    return entry.summary ?? "";
  }

  // Extract person ID and slide number from current route
  $: currentPath = $location;
  $: storyMatch = currentPath.match(/^\/story\/([^/]+)(?:\/(\d+))?/);
  $: exhibitionMatch = currentPath.match(/^\/exhibition\/([^/]+)/);
  $: personId = storyMatch
    ? decodeURIComponent(storyMatch[1])
    : exhibitionMatch
      ? decodeURIComponent(exhibitionMatch[1])
      : null;
  $: slideParam =
    storyMatch && storyMatch[2] ? parseInt(storyMatch[2], 10) : null;

  // Reactive data loading - load when personId changes
  let dataset = null;
  let egoNetwork = null;
  let dataLoading = false;
  let loadingStage = null; // Track which part is loading: 'initial', 'dataset', 'network', null

  $: if (personId) {
    dataLoading = true;
    loadingStage = "initial";
    dataset = null;
    egoNetwork = null;

    // Load dataset first (includes portrait and events)
    loadingStage = "dataset";
    loadDataset(personId)
      .then((datasetResult) => {
        dataset = datasetResult;
        loadingStage = "network";
        // Load network data after dataset
        return loadEgoNetwork(personId);
      })
      .then((networkResult) => {
        egoNetwork = networkResult;
        dataLoading = false;
        loadingStage = null;
      })
      .catch((error) => {
        console.error("Failed to load data:", error);
        dataset = null;
        egoNetwork = null;
        dataLoading = false;
        loadingStage = null;
      });
  } else {
    dataset = null;
    egoNetwork = null;
    dataLoading = false;
    loadingStage = null;
  }

  // Normalise a display name (underscore to space, collapse whitespace)
  function displayName(value = "") {
    if (typeof value !== "string") return "";
    return value.replace(/_/g, " ").replace(/\s+/g, " ").trim();
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
    push("/");
  }

  function handleSelectPerson(event) {
    const id = event.detail;
    if (id) {
      push(`/story/${encodeURIComponent(id)}`);
    }
  }

  function handleCloseStory() {
    push("/");
  }

  function handleSlideChange(event) {
    const slideIndex = event.detail;
    if (personId && slideIndex !== null && slideIndex !== undefined) {
      // Update URL with current slide, but use replace to avoid cluttering history
      const newPath =
        slideIndex === 0
          ? `/story/${encodeURIComponent(personId)}`
          : `/story/${encodeURIComponent(personId)}/${slideIndex}`;

      // Use replace instead of push to avoid filling up history
      if (currentPath !== newPath) {
        replace(newPath);
      }
    }
  }
</script>

<div class="shell">
  {#if currentPath.startsWith("/exhibition/")}
    <ExhibitionView
      {dataset}
      isLoading={dataLoading}
      styleConfig={styleFor(personId)}
    />
  {:else if currentPath.startsWith("/story/")}
    <StoryView
      {dataset}
      {egoNetwork}
      isLoading={dataLoading}
      {loadingStage}
      activeIndex={slideParam ?? 0}
      hasRegistryEntries={registryEntries.length > 0}
      styleConfig={styleFor(personId)}
      onClose={handleCloseStory}
      onSlideChange={handleSlideChange}
    />
  {:else}
    <Landing
      entries={registryEntries}
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
