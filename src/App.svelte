<script>
  import Landing from "./components/Landing.svelte";
  import StoryView from "./components/StoryView.svelte";
  import registry from "../data/persons.json";
  import styleRegistry from "../data/person_styles.json";

  const datasetModules = import.meta.glob("../data/people/*_life_events.json", {
    eager: true,
    import: "default",
  });

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function isHexColor(value) {
    return typeof value === "string" && /^#[0-9a-fA-F]{6}$/.test(value.trim());
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
    if (
      typeof raw.pattern_opacity === "number" &&
      Number.isFinite(raw.pattern_opacity)
    ) {
      result.patternOpacity = clamp(raw.pattern_opacity, 0, 1);
    }
    return Object.keys(result).length > 0 ? result : null;
  }

  const defaultStyleBase = {
    primary: "#38BDF8",
    secondary: "#FACC15",
    background: "#0F172A",
    background_pattern_svg:
      '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160"><rect width="160" height="160" fill="#000000"/><path fill="#FFFFFF" d="M0 0h20v20H0zM40 40h20v20H40zM80 0h20v20H80zM120 40h20v20h-20zM0 80h20v20H0zM80 80h20v20H80zM40 120h20v20H40zM120 120h20v20h-20z"/></svg>',
    pattern_opacity: 0.16,
  };

  const defaultStyle = (() => {
    const normalised = normaliseStyle(defaultStyleBase) ?? {};
    return {
      primary: normalised.primary ?? defaultStyleBase.primary,
      secondary: normalised.secondary ?? defaultStyleBase.secondary,
      background: normalised.background ?? defaultStyleBase.background,
      backgroundPatternSvg:
        normalised.backgroundPatternSvg ??
        defaultStyleBase.background_pattern_svg,
      backgroundPatternDataUrl:
        normalised.backgroundPatternDataUrl ??
        svgToDataUrl(defaultStyleBase.background_pattern_svg),
      patternOpacity:
        normalised.patternOpacity ?? defaultStyleBase.pattern_opacity,
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
      const fileName = segments[segments.length - 1] ?? "";
      const id = fileName.replace("_life_events.json", "");
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
          file: `people/${id}_life_events.json`,
        })
      );
    }
    entries.sort((a, b) => a.name.localeCompare(b.name));
    return entries;
  })();

  let selectedPersonId = null;
  let previousPersonId = null;
  let activeIndex = 0;

  $: dataset = selectedPersonId ? (datasetMap[selectedPersonId] ?? null) : null;
  $: if (selectedPersonId !== previousPersonId) {
    activeIndex = 0;
    previousPersonId = selectedPersonId;
  }

  function openStory(id) {
    if (!id) return;
    if (!datasetMap[id]) return;
    selectedPersonId = id;
  }

  function closeStory() {
    selectedPersonId = null;
  }

  function entrySummary(entry) {
    if (!entry?.id) return "";
    return entry.summary ?? datasetMap[entry.id]?.person?.summary ?? "";
  }
</script>

<div class="shell">
  {#if selectedPersonId}
    <StoryView
      bind:activeIndex
      {dataset}
      hasRegistryEntries={registryEntries.length > 0}
      styleConfig={styleFor(selectedPersonId)}
      on:close={closeStory}
    />
  {:else}
    <Landing
      entries={registryEntries}
      getSummary={entrySummary}
      getStyle={(id) => styleFor(id)}
      on:selectPerson={(event) => openStory(event.detail)}
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
