<script>
  import { push, pop, replace, location } from "svelte-spa-router";
  import Landing from "./components/Landing.svelte";
  import StoryView from "./components/StoryView.svelte";
  import registry from "../data/persons.json";
  import styleRegistry from "../data/person_styles.json";

  const datasetModules = import.meta.glob("../data/people/*/life_events.json", {
    eager: true,
    import: "default",
  });

  const egoNetworkModules = import.meta.glob(
    "../data/people/*/ego_network.json",
    {
      eager: true,
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
    };
  }

  const datasetMap = Object.entries(datasetModules).reduce(
    (accumulator, [path, data]) => {
      const segments = path.split("/");
      // Path format: ../data/people/<person_id>/life_events.json
      // Get the person_id from second-to-last segment
      const id = segments[segments.length - 2] ?? "";
      accumulator[id] = data;
      return accumulator;
    },
    {}
  );

  const egoNetworkMap = Object.entries(egoNetworkModules).reduce(
    (accumulator, [path, data]) => {
      const segments = path.split("/");
      const id = segments[segments.length - 2] ?? "";
      accumulator[id] = data;
      return accumulator;
    },
    {}
  );

  function computeYearsLabel(person = {}) {
    const toYear = (value) => {
      if (!value) return null;
      const parsed = new Date(value);
      const year = parsed.getFullYear();
      return Number.isNaN(year) ? null : year;
    };
    const birthYear = toYear(person.birth_date);
    const deathYear = toYear(person.death_date);
    if (birthYear && deathYear) {
      return `${birthYear} - ${deathYear}`;
    }
    if (birthYear) {
      return `${birthYear}`;
    }
    return "";
  }

  function derivePrimaryRoles(person = {}) {
    if (!Array.isArray(person.primary_roles)) {
      return [];
    }
    return person.primary_roles.slice(0, 3);
  }

  function enrichEntry(baseEntry) {
    if (!baseEntry?.id) {
      return baseEntry;
    }
    const dataset = datasetMap[baseEntry.id] ?? null;
    const person = dataset?.person ?? {};
    return {
      ...baseEntry,
      summary: baseEntry.summary ?? person.summary ?? "",
      portrait: person.portrait ?? null,
      lifespan: computeYearsLabel(person),
      primaryRoles: derivePrimaryRoles(person),
      style: styleFor(baseEntry.id),
    };
  }

  const registryEntries = (() => {
    const entries = [];
    const seen = new Set();
    if (Array.isArray(registry?.people)) {
      for (const entry of registry.people) {
        if (!entry?.id) continue;
        if (!datasetMap[entry.id]) continue;
        entries.push(enrichEntry(entry));
        seen.add(entry.id);
      }
    }
    for (const id of Object.keys(datasetMap)) {
      if (seen.has(id)) continue;
      const data = datasetMap[id];
      const fallbackName = data?.person?.name ?? id.replace(/_/g, " ");
      entries.push(
        enrichEntry({
          id,
          name: fallbackName,
          file: `people/${id}/life_events.json`,
        })
      );
    }
    entries.sort((a, b) => a.name.localeCompare(b.name));
    return entries;
  })();

  function entrySummary(entry) {
    if (!entry?.id) return "";
    return entry.summary ?? datasetMap[entry.id]?.person?.summary ?? "";
  }

  // Extract person ID and slide number from current route
  $: currentPath = $location;
  $: storyMatch = currentPath.match(/^\/story\/([^/]+)(?:\/(\d+))?/);
  $: personId = storyMatch ? decodeURIComponent(storyMatch[1]) : null;
  $: slideParam =
    storyMatch && storyMatch[2] ? parseInt(storyMatch[2], 10) : null;
  $: dataset = personId ? (datasetMap[personId] ?? null) : null;
  $: egoNetwork = personId ? (egoNetworkMap[personId] ?? null) : null;

  // Redirect to home if trying to view non-existent story
  $: if (storyMatch && !dataset && personId) {
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
  {#if currentPath.startsWith("/story/") && dataset}
    <StoryView
      {dataset}
      {egoNetwork}
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
  }

  :global(:root) {
    --header-height: 11.5rem;
  }

  .shell {
    min-height: 100vh;
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
