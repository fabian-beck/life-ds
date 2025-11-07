<script>
  import Landing from "./components/Landing.svelte";
  import StoryView from "./components/StoryView.svelte";
  import registry from "../data/persons.json";

  const datasetModules = import.meta.glob("../data/people/*_life_events.json", {
    eager: true,
    import: "default",
  });

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
      on:close={closeStory}
    />
  {:else}
    <Landing
      entries={registryEntries}
      getSummary={entrySummary}
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
