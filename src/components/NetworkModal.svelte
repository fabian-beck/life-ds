<script>
  import { mdiAccountMultipleOutline } from "@mdi/js";
  import PersonChip from "./PersonChip.svelte";
  import CloseButton from "./CloseButton.svelte";
  import { _ } from "../stores/language";
  import { storyStyleVars } from "../utils/helpers.js";
  import {
    normalizePersonName,
    generateNameVariants,
  } from "../utils/storyHelpers.js";

  export let egoNetwork = null;
  export let personName = "";
  export let styleConfig = null;
  export let onClose = () => {};

  let visiblePersonInfo = null;

  /**
   * Parse text and highlight person names and unique subcategories from the network
   * @param {string} text - Text to parse
   * @param {Array} connections - Array of connection objects
   * @returns {Array} Array of segments with type 'text' or 'person'
   */
  function parseTextWithPeople(text, connections = []) {
    if (!text || !connections.length) {
      return [{ type: 'text', content: text || '' }];
    }

    const allMatches = [];

    // Step 1: Find unique subcategories (only those assigned to one person)
    const subcategoryCounts = new Map();
    for (const conn of connections) {
      const subcategory = getSubcategory(conn.relationship_type);
      if (subcategory) {
        const count = subcategoryCounts.get(subcategory) || 0;
        subcategoryCounts.set(subcategory, count + 1);
      }
    }

    // Build a list of unique subcategories and their associated person
    const uniqueSubcategories = [];
    for (const conn of connections) {
      const subcategory = getSubcategory(conn.relationship_type);
      if (subcategory && subcategoryCounts.get(subcategory) === 1) {
        uniqueSubcategories.push({ subcategory, person: conn });
      }
    }

    // Match unique subcategories in the text
    for (const { subcategory, person } of uniqueSubcategories) {
      // Create a word-boundary regex for the subcategory
      const regex = new RegExp(`\\b${subcategory}\\b`, 'gi');
      let match;

      while ((match = regex.exec(text)) !== null) {
        allMatches.push({
          start: match.index,
          end: regex.lastIndex,
          person,
          matchedText: match[0],
          priority: 5, // Lower priority than full names
          type: 'subcategory',
        });
      }
    }

    // Step 2: Find person name matches
    const lastNameCounts = new Map();
    for (const conn of connections) {
      const normalized = normalizePersonName(conn.person_name);
      if (normalized) {
        const count = lastNameCounts.get(normalized.lastName) || 0;
        lastNameCounts.set(normalized.lastName, count + 1);
      }
    }

    for (const conn of connections) {
      const normalized = normalizePersonName(conn.person_name);
      const variants = generateNameVariants(conn.person_name);
      const hasAmbiguousLastName = normalized && lastNameCounts.get(normalized.lastName) > 1;

      let bestMatch = null;

      for (const variant of variants) {
        // Skip last-name-only matches if ambiguous
        if (hasAmbiguousLastName && variant.type === 'last') {
          continue;
        }

        let match;
        variant.regex.lastIndex = 0;

        while ((match = variant.regex.exec(text)) !== null) {
          const start = match.index;
          const end = variant.regex.lastIndex;

          const candidate = {
            start,
            end,
            person: conn,
            matchedText: match[0],
            priority: variant.priority,
            type: 'person',
          };

          if (!bestMatch ||
              candidate.priority < bestMatch.priority ||
              (candidate.priority === bestMatch.priority && candidate.matchedText.length > bestMatch.matchedText.length)) {
            bestMatch = candidate;
          }
        }
      }

      if (bestMatch) {
        allMatches.push(bestMatch);
      }
    }

    // Step 3: Sort by position and priority, then remove overlaps
    const sortedMatches = allMatches.sort((a, b) => {
      if (a.start !== b.start) return a.start - b.start;
      // If same position, prefer lower priority (person names over subcategories)
      return a.priority - b.priority;
    });

    const filteredMatches = [];
    let lastEnd = 0;

    for (const match of sortedMatches) {
      if (match.start >= lastEnd) {
        filteredMatches.push(match);
        lastEnd = match.end;
      }
    }

    // Step 4: Build segments
    const segments = [];
    let currentPos = 0;

    for (const match of filteredMatches) {
      if (match.start > currentPos) {
        segments.push({
          type: 'text',
          content: text.slice(currentPos, match.start),
        });
      }

      segments.push({
        type: 'person',
        content: match.matchedText,
        person: match.person,
      });

      currentPos = match.end;
    }

    if (currentPos < text.length) {
      segments.push({
        type: 'text',
        content: text.slice(currentPos),
      });
    }

    return segments;
  }

  function groupPeopleByType(connections) {
    const groups = {};
    connections.forEach((connection) => {
      const fullType = connection.relationship_type || "other";
      // Extract the main category (before the slash)
      const mainCategory = fullType.includes("/")
        ? fullType.split("/")[0]
        : fullType;

      if (!groups[mainCategory]) {
        groups[mainCategory] = [];
      }
      groups[mainCategory].push(connection);
    });
    return groups;
  }

  /**
   * Group connections by subcategory if subcategories repeat (≥2 occurrences)
   * @param {Array} connections - Array of connection objects
   * @returns {Array} Array of {subcategory, label, people} objects
   */
  function groupBySubcategory(connections) {
    // Count subcategory occurrences
    const subcategoryCounts = new Map();
    connections.forEach((conn) => {
      const subcategory = getSubcategory(conn.relationship_type);
      if (subcategory) {
        const count = subcategoryCounts.get(subcategory) || 0;
        subcategoryCounts.set(subcategory, count + 1);
      }
    });

    // Find repeated subcategories (≥2 occurrences)
    const repeatedSubcategories = new Set();
    subcategoryCounts.forEach((count, subcategory) => {
      if (count >= 2) {
        repeatedSubcategories.add(subcategory);
      }
    });

    // If no repeated subcategories, return ungrouped
    if (repeatedSubcategories.size === 0) {
      return [{ subcategory: null, label: null, people: sortByStrength(connections) }];
    }

    // Group by subcategory
    const groups = new Map();
    const ungrouped = [];

    connections.forEach((conn) => {
      const subcategory = getSubcategory(conn.relationship_type);
      if (subcategory && repeatedSubcategories.has(subcategory)) {
        if (!groups.has(subcategory)) {
          groups.set(subcategory, []);
        }
        groups.get(subcategory).push(conn);
      } else {
        ungrouped.push(conn);
      }
    });

    // Convert to array with accumulated strength scores
    const groupsArray = [];
    groups.forEach((people, subcategory) => {
      const accumulatedStrength = calculateAccumulatedStrength(people);
      groupsArray.push({
        subcategory,
        label: capitalizeSubcategory(subcategory),
        people: sortByStrength(people),
        accumulatedStrength,
      });
    });

    // Sort by accumulated strength (lower is stronger)
    groupsArray.sort((a, b) => a.accumulatedStrength - b.accumulatedStrength);

    // Add ungrouped people at the end (always last)
    if (ungrouped.length > 0) {
      groupsArray.push({
        subcategory: null,
        label: 'Other',
        people: sortByStrength(ungrouped),
        accumulatedStrength: Infinity, // Ensures it's always last
      });
    }

    return groupsArray;
  }

  /**
   * Calculate accumulated strength score for a group of connections
   * Lower score = stronger overall connections
   * @param {Array} connections - Array of connection objects
   * @returns {number} Accumulated strength score
   */
  function calculateAccumulatedStrength(connections) {
    const strengthOrder = { strong: 0, moderate: 1, weak: 2 };
    return connections.reduce((sum, conn) => {
      return sum + (strengthOrder[conn.strength] ?? 3);
    }, 0);
  }

  function capitalizeSubcategory(subcategory) {
    if (!subcategory) return '';
    return subcategory
      .split('-')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }

  function subdivideFamilyMembers(familyConnections) {
    const parents = [];
    const spouses = [];
    const children = [];
    const otherRelatives = [];

    const parentTypes = ["mother", "father", "parent"];
    const spouseTypes = ["spouse", "partner", "husband", "wife"];
    const childTypes = ["son", "daughter", "child"];

    familyConnections.forEach((connection) => {
      const subcategory = getSubcategory(connection.relationship_type);
      if (subcategory && parentTypes.includes(subcategory)) {
        parents.push(connection);
      } else if (subcategory && spouseTypes.includes(subcategory)) {
        spouses.push(connection);
      } else if (subcategory && childTypes.includes(subcategory)) {
        children.push(connection);
      } else {
        otherRelatives.push(connection);
      }
    });

    return {
      parents: sortByStrength(parents),
      spouses: sortByStrength(spouses),
      children: sortByStrength(children),
      otherRelatives: sortByStrength(otherRelatives),
    };
  }

  function sortByStrength(connections) {
    const strengthOrder = { strong: 0, moderate: 1, weak: 2 };
    return connections.sort((a, b) => {
      const aStrength = strengthOrder[a.strength] ?? 3;
      const bStrength = strengthOrder[b.strength] ?? 3;
      return aStrength - bStrength;
    });
  }

  function getSubcategory(relationshipType) {
    if (!relationshipType || !relationshipType.includes("/")) {
      return null;
    }
    return relationshipType.split("/")[1];
  }

  function togglePersonInfo(personKey) {
    if (visiblePersonInfo === personKey) {
      visiblePersonInfo = null;
    } else {
      visiblePersonInfo = personKey;
    }
  }

  function handleClickOutside(event) {
    const personWrapper = event.target.closest(".person-info-wrapper");
    if (!personWrapper && visiblePersonInfo !== null) {
      visiblePersonInfo = null;
    }
  }

  $: connections = egoNetwork?.connections || [];
  $: groupedPeople = groupPeopleByType(connections);
  $: categorySummaries = egoNetwork?.category_summaries || [];

  // Create a map for quick lookup of summaries by type
  $: summaryMap = categorySummaries.reduce((map, item) => {
    map[item.relationship_type] = item.summary;
    return map;
  }, {});
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="modal-overlay" on:click={onClose}>
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    class="network-modal"
    style={storyStyleVars(styleConfig)}
    on:click|stopPropagation
  >
    <div class="modal-header">
      <h3 class="modal-title">
        <svg
          class="icon"
          viewBox="0 0 24 24"
          role="presentation"
          aria-hidden="true"
        >
          <path d={mdiAccountMultipleOutline} />
        </svg>
        {$_("network.title", { name: personName })}
      </h3>
      <CloseButton
        variant="dark"
        size="medium"
        ariaLabel={$_("network.close")}
        on:click={onClose}
      />
    </div>
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div class="modal-content" on:click={handleClickOutside}>
      {#each Object.entries(groupedPeople).sort(([a], [b]) => {
        if (a === "family") return -1;
        if (b === "family") return 1;
        return a.localeCompare(b);
      }) as [type, people]}
        {#if type === "family"}
          {@const familySubgroups = subdivideFamilyMembers(people)}
          <div class="person-group">
            <h4 class="group-title">
              {type}
              <span class="group-count"
                >{$_("network.group_count", { count: people.length })}</span
              >
            </h4>
            <div class="group-layout">
              <div class="group-description">
                {#if summaryMap[type]}
                  {@const summarySegments = parseTextWithPeople(summaryMap[type], people)}
                  <p class="category-summary">{#each summarySegments as segment}{#if segment.type === 'text'}{segment.content}{:else}<strong class="person-mention">{segment.content}</strong>{/if}{/each}</p>
                {/if}
              </div>

              <div class="group-connections">
                {#if familySubgroups.parents.length > 0}
                  <h5 class="subgroup-title">Parents</h5>
                  <div class="group-people">
                    {#each familySubgroups.parents as person, idx}
                      {@const personKey = `family-parents-${idx}`}
                      {@const subcategory = getSubcategory(
                        person.relationship_type
                      )}
                      <PersonChip
                        {person}
                        {personKey}
                        {visiblePersonInfo}
                        {subcategory}
                        {styleConfig}
                        onToggle={togglePersonInfo}
                        containerSelector=".modal-content"
                      />
                    {/each}
                  </div>
                {/if}

                {#if familySubgroups.spouses.length > 0}
                  <h5 class="subgroup-title">Spouse/Partner</h5>
                  <div class="group-people">
                    {#each familySubgroups.spouses as person, idx}
                      {@const personKey = `family-spouses-${idx}`}
                      {@const subcategory = getSubcategory(
                        person.relationship_type
                      )}
                      <PersonChip
                        {person}
                        {personKey}
                        {visiblePersonInfo}
                        {subcategory}
                        {styleConfig}
                        onToggle={togglePersonInfo}
                        containerSelector=".modal-content"
                      />
                    {/each}
                  </div>
                {/if}

                {#if familySubgroups.children.length > 0}
                  <h5 class="subgroup-title">Children</h5>
                  <div class="group-people">
                    {#each familySubgroups.children as person, idx}
                      {@const personKey = `family-children-${idx}`}
                      {@const subcategory = getSubcategory(
                        person.relationship_type
                      )}
                      <PersonChip
                        {person}
                        {personKey}
                        {visiblePersonInfo}
                        {subcategory}
                        {styleConfig}
                        onToggle={togglePersonInfo}
                        containerSelector=".modal-content"
                      />
                    {/each}
                  </div>
                {/if}

                {#if familySubgroups.otherRelatives.length > 0}
                  <h5 class="subgroup-title">Other Relatives</h5>
                  <div class="group-people">
                    {#each familySubgroups.otherRelatives as person, idx}
                      {@const personKey = `family-other-${idx}`}
                      {@const subcategory = getSubcategory(
                        person.relationship_type
                      )}
                      <PersonChip
                        {person}
                        {personKey}
                        {visiblePersonInfo}
                        {subcategory}
                        {styleConfig}
                        onToggle={togglePersonInfo}
                        containerSelector=".modal-content"
                      />
                    {/each}
                  </div>
                {/if}
              </div>
            </div>
          </div>
        {:else}
          {@const subgroups = groupBySubcategory(people)}
          <div class="person-group">
            <h4 class="group-title">
              {type}
              <span class="group-count"
                >{$_("network.group_count", { count: people.length })}</span
              >
            </h4>
            <div class="group-layout">
              <div class="group-description">
                {#if summaryMap[type]}
                  {@const summarySegments = parseTextWithPeople(summaryMap[type], people)}
                  <p class="category-summary">{#each summarySegments as segment}{#if segment.type === 'text'}{segment.content}{:else}<strong class="person-mention">{segment.content}</strong>{/if}{/each}</p>
                {/if}
              </div>

              <div class="group-connections">
                {#each subgroups as subgroup}
                  {#if subgroup.label}
                    <h5 class="subgroup-title">{subgroup.label}</h5>
                  {/if}
                  <div class="group-people">
                    {#each subgroup.people as person, idx}
                      {@const personKey = `${type}-${subgroup.subcategory || 'default'}-${idx}`}
                      {@const subcategory = getSubcategory(person.relationship_type)}
                      <PersonChip
                        {person}
                        {personKey}
                        {visiblePersonInfo}
                        {subcategory}
                        {styleConfig}
                        onToggle={togglePersonInfo}
                        containerSelector=".modal-content"
                      />
                    {/each}
                  </div>
                {/each}
              </div>
            </div>
          </div>
        {/if}
      {/each}
    </div>
  </div>
</div>

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: fadeIn 0.2s ease;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  .network-modal {
    width: 100%;
    height: 100%;
    max-width: 100vw;
    max-width: 100dvw;
    max-height: 100vh;
    max-height: 100dvh;
    display: flex;
    flex-direction: column;
    animation: fadeIn 0.2s ease;
    position: relative;
    overflow: hidden;
    background: rgba(15, 23, 42, 0.6);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(148, 163, 184, 0.3);
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.3);
  }

  .modal-header,
  .modal-content {
    position: relative;
  }

  .modal-header {
    padding: 1rem 1.25rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .modal-title {
    margin: 0;
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--story-primary, #f8fafc);
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-family: var(--story-heading-font, Inter, sans-serif);
  }

  .modal-title .icon {
    color: var(--story-secondary, #38bdf8);
  }

  .icon {
    width: 1.25rem;
    height: 1.25rem;
    fill: currentColor;
    flex: 0 0 auto;
  }

  .modal-content {
    padding: 1.25rem;
    overflow-y: auto;
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .person-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .group-layout {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .group-description {
    flex: 1 1 auto;
  }

  .group-connections {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .category-summary {
    margin: 0;
    font-size: 0.85rem;
    line-height: 1.5;
    color: #e2e8f0;
    font-family: var(--story-body-font, Inter, sans-serif);
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
  }

  .group-title {
    margin: 0;
    font-size: 0.9rem;
    text-transform: capitalize;
    color: var(--story-primary, #f8fafc);
    font-weight: 600;
    font-family: var(--story-heading-font, Inter, sans-serif);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    letter-spacing: 0.01em;
  }

  .group-count {
    font-size: 0.75rem;
    color: var(--story-secondary, #38bdf8);
    font-weight: 600;
  }

  .subgroup-title {
    margin: 0.25rem 0 0.15rem 0;
    font-size: 0.75rem;
    text-transform: capitalize;
    color: rgba(226, 232, 240, 0.85);
    font-weight: 500;
    font-family: var(--story-body-font, Inter, sans-serif);
    letter-spacing: 0.01em;
    text-align: center;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }

  .subgroup-title::before,
  .subgroup-title::after {
    content: "";
    display: block;
    width: 2rem;
    height: 1px;
    background: linear-gradient(
      to right,
      transparent,
      rgba(226, 232, 240, 0.3),
      transparent
    );
  }

  .subgroup-title::before {
    background: linear-gradient(to left, rgba(226, 232, 240, 0.3), transparent);
  }

  .subgroup-title::after {
    background: linear-gradient(
      to right,
      rgba(226, 232, 240, 0.3),
      transparent
    );
  }

  .group-people {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    justify-content: center;
  }

  /* Person name highlighting */
  .person-mention {
    font-weight: bold;
    text-shadow: 0 0 4px var(--story-secondary, rgba(56, 189, 248, 0.25));
  }

  @media (min-width: 768px) {
    .network-modal {
      max-width: 900px;
      max-height: 90vh;
      max-height: 90dvh;
      border-radius: 1rem;
    }

    .modal-content {
      padding: 1.5rem;
    }

    .modal-header {
      padding: 1.25rem 1.5rem;
    }

    /* Two-column layout for wider screens */
    .group-layout {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.5rem;
      align-items: start;
    }

    .group-description {
      grid-column: 1;
    }

    .group-connections {
      grid-column: 2;
    }
  }
</style>
