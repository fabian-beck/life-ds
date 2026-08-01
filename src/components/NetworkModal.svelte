<script>
  import { afterUpdate, onMount } from "svelte";
  import { mdiAccount, mdiAccountMultipleOutline } from "@mdi/js";
  import PersonChip from "./PersonChip.svelte";
  import CloseButton from "./CloseButton.svelte";
  import { _ } from "../stores/language";
  import { dialog } from "../utils/dialog.js";
  import { storyStyleVars } from "../utils/helpers.js";
  import { escapeRegex } from "../utils/storyHelpers.js";
  import { findPersonMentions } from "../utils/personNames.js";
  import {
    relationshipCategoryLabel,
    relationshipRoleLabel,
  } from "../utils/relationshipLabels.js";
  import { assetUrl } from "../utils/assetUrl.js";

  export let egoNetwork = null;
  export let personName = "";
  export let portrait = null;
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
      return [{ type: "text", content: text || "" }];
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
      // Create a word-boundary regex for the subcategory (escaped: values come
      // from data and may contain regex metacharacters)
      const regex = new RegExp(`\\b${escapeRegex(subcategory)}\\b`, "gi");
      let match;

      while ((match = regex.exec(text)) !== null) {
        allMatches.push({
          start: match.index,
          end: regex.lastIndex,
          person,
          matchedText: match[0],
          priority: 5, // Lower priority than full names
          type: "subcategory",
        });
      }
    }

    // Step 2: Find person name matches (shared matcher — same rules the story
    // slides and meta story prose use).
    for (const match of findPersonMentions(text, connections)) {
      allMatches.push({
        start: match.start,
        end: match.end,
        person: match.person,
        matchedText: text.slice(match.start, match.end),
        priority: 1,
        type: "person",
      });
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
          type: "text",
          content: text.slice(currentPos, match.start),
        });
      }

      segments.push({
        type: "person",
        content: match.matchedText,
        person: match.person,
      });

      currentPos = match.end;
    }

    if (currentPos < text.length) {
      segments.push({
        type: "text",
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
      return [
        { subcategory: null, label: null, people: sortByStrength(connections) },
      ];
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
        label: subcategoryLabel(subcategory, people.length),
        people: sortByStrength(people),
        accumulatedStrength,
      });
    });

    // Sort by accumulated strength (lower is stronger)
    groupsArray.sort((a, b) => a.accumulatedStrength - b.accumulatedStrength);

    // Add ungrouped people at the end (always last)
    if (ungrouped.length > 0) {
      // A lone leftover that has its own subcategory needs no generic "Other"
      // box: name the box after that subcategory and let the person drop its
      // now-redundant role label (showRole is off once the box has a subcategory).
      const soleSubcategory =
        ungrouped.length === 1
          ? getSubcategory(ungrouped[0].relationship_type)
          : null;
      groupsArray.push({
        subcategory: soleSubcategory,
        label: soleSubcategory ? subcategoryLabel(soleSubcategory, 1) : null,
        isOther: !soleSubcategory, // Labeled "Other" (translated) in the template
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

  // A box label names a repeated subcategory. `relationship_type` is a machine
  // token the datasets keep untranslated in every language, so it is resolved
  // through the locale rather than merely capitalized — which is also what
  // stops two children from being labeled "Childs".
  function subcategoryLabel(subcategory, count = 1) {
    return relationshipRoleLabel($_, subcategory, count);
  }

  // Family layout: three generation layers, each holding "boxes" of people
  // who belong together (couples, siblings, in-laws, ...). Keys are matched
  // against normalized relationship subcategories (see
  // normalizeFamilySubcategory); anything unmatched lands in "Other Relatives".
  const SPOUSE_KEYS = new Set([
    "spouse",
    "partner",
    "husband",
    "wife",
    "consort",
    "fiance",
    "fiancee",
    "fiancé",
    "fiancée",
  ]);

  const FAMILY_GENERATIONS = [
    {
      layer: "grandparents",
      boxes: [
        {
          id: "grandparents",
          labelKey: "network.family.grandparents",
          keys: ["grandfather", "grandmother", "grandparent", "grandparents"],
        },
      ],
    },
    {
      // Ordered so "parents" comes last: when boxes stack on narrow
      // viewports, the box next to the generation link is on the bloodline.
      layer: "older",
      boxes: [
        {
          id: "aunts_uncles",
          labelKey: "network.family.aunts_uncles",
          keys: ["aunt", "uncle", "godfather", "godmother", "godparent"],
        },
        {
          id: "in_laws_older",
          labelKey: "network.family.in_laws",
          keys: ["father-in-law", "mother-in-law", "parent-in-law"],
        },
        {
          id: "parents",
          labelKey: "network.family.parents",
          keys: ["father", "mother", "parent", "parents"],
        },
      ],
    },
    {
      layer: "ego",
      boxes: [
        {
          id: "siblings",
          labelKey: "network.family.siblings",
          keys: ["sibling", "siblings", "brother", "sister", "twin"],
        },
        {
          id: "in_laws_ego",
          labelKey: "network.family.in_laws",
          keys: ["brother-in-law", "sister-in-law", "sibling-in-law"],
        },
        {
          id: "cousins",
          labelKey: "network.family.cousins",
          keys: ["cousin", "cousins"],
        },
      ],
    },
    {
      layer: "younger",
      boxes: [
        {
          id: "children",
          labelKey: "network.family.children",
          keys: ["child", "children", "son", "daughter"],
        },
        {
          id: "in_laws_younger",
          labelKey: "network.family.in_laws",
          keys: ["son-in-law", "daughter-in-law", "child-in-law"],
        },
        {
          id: "grandchildren",
          labelKey: "network.family.grandchildren",
          keys: ["grandchild", "grandchildren", "grandson", "granddaughter"],
        },
        {
          id: "nieces_nephews",
          labelKey: "network.family.nieces_nephews",
          keys: ["niece", "nephew"],
        },
      ],
    },
  ];

  /**
   * Normalize a family relationship subcategory to a canonical key:
   * lowercased, hyphenated, with step/half/biological/etc. prefixes and
   * "-by-marriage" suffixes stripped (e.g. "biological_father" -> "father",
   * "aunt-by-marriage" -> "aunt", "half_sibling" -> "sibling").
   */
  function normalizeFamilySubcategory(relationshipType) {
    const subcategory = getSubcategory(relationshipType);
    if (!subcategory) return null;
    return subcategory
      .toLowerCase()
      .replace(/[\s_]+/g, "-")
      .replace(/-by-marriage$/, "")
      .replace(/^(step|half|adoptive|adopted|biological|foster)-?/, "");
  }

  /**
   * Group family connections into three generation rows (older / ego /
   * younger) of boxes, plus a trailing list of unclassifiable relatives.
   * The ego row always exists and leads with the ego + spouses box.
   */
  function buildFamilyGenerations(familyConnections) {
    const keyToBox = new Map();
    for (const generation of FAMILY_GENERATIONS) {
      for (const box of generation.boxes) {
        for (const key of box.keys) {
          keyToBox.set(key, box.id);
        }
      }
    }

    const membersByBox = new Map();
    const spouses = [];
    const other = [];

    for (const connection of familyConnections) {
      const key = normalizeFamilySubcategory(connection.relationship_type);
      if (key && SPOUSE_KEYS.has(key)) {
        spouses.push(connection);
        continue;
      }
      const boxId = key ? keyToBox.get(key) : null;
      if (boxId) {
        if (!membersByBox.has(boxId)) {
          membersByBox.set(boxId, []);
        }
        membersByBox.get(boxId).push(connection);
      } else {
        other.push(connection);
      }
    }

    const rows = FAMILY_GENERATIONS.map((generation) => ({
      layer: generation.layer,
      boxes: generation.boxes
        .filter((box) => membersByBox.has(box.id))
        .map((box) => ({
          id: box.id,
          labelKey: box.labelKey,
          people: sortByStrength(membersByBox.get(box.id)),
        })),
    }));

    const grandRow = rows.find((row) => row.layer === "grandparents");
    const olderRow = rows.find((row) => row.layer === "older");
    const egoRow = rows.find((row) => row.layer === "ego");
    const youngerRow = rows.find((row) => row.layer === "younger");

    // The parents -> ego line starts at the parents' generation's last box
    // (parents when present — see box ordering above), falling back to the
    // grandparents when no parents' generation exists
    const egoSourceRow =
      olderRow.boxes.length > 0
        ? olderRow
        : grandRow.boxes.length > 0
          ? grandRow
          : null;

    // Ego box (ego + spouses/partners) closes the middle row so that, when
    // boxes stack, it sits directly above the link to the younger generation.
    egoRow.boxes.push({
      id: "ego",
      labelKey: spouses.length > 0 ? "network.family.spouse_partner" : null,
      isEgo: true,
      linkUp: egoSourceRow !== null,
      people: sortByStrength(spouses),
    });

    if (egoSourceRow) {
      egoSourceRow.boxes[egoSourceRow.boxes.length - 1].linkSource = true;
      // Siblings descend from the same parents: box-to-box link upward
      const siblingsBox = egoRow.boxes.find((box) => box.id === "siblings");
      if (siblingsBox) {
        siblingsBox.linkUpBox = true;
      }
    }

    // Grandparents sit a layer above the parents' generation, linked by a
    // downward box-to-box stub (when no parents' generation exists, the
    // parents -> ego line already covers the connection)
    if (grandRow.boxes.length > 0 && olderRow.boxes.length > 0) {
      grandRow.boxes[grandRow.boxes.length - 1].linkDownBox = true;
    }

    // The couple -> descendants line ends at the descendants box; no link
    // when the younger generation holds just nieces/nephews or children-in-law
    const descendantsBox =
      youngerRow.boxes.find((box) => box.id === "children") ??
      youngerRow.boxes.find((box) => box.id === "grandchildren");
    if (descendantsBox) {
      descendantsBox.linkTarget = true;
    }

    return {
      rows: rows.filter((row) => row.boxes.length > 0),
      other: sortByStrength(other),
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

  let familyGenerationsEl = null;

  /**
   * Draw one vertical link at viewport x from topY to bottomY. Segments
   * crossing boxes other than the excluded endpoints are made transparent so
   * the line passes "behind" them.
   */
  function drawVerticalLink(line, containerRect, x, topY, bottomY, excluded) {
    const height = bottomY - topY;
    if (height <= 0) {
      line.style.display = "none";
      return;
    }

    const intervals = [];
    for (const box of familyGenerationsEl.querySelectorAll(".family-box")) {
      if (excluded.includes(box)) continue;
      const rect = box.getBoundingClientRect();
      if (rect.left > x || rect.right < x) continue;
      const start = Math.max(0, rect.top - topY);
      const end = Math.min(height, rect.bottom - topY);
      if (end > start) intervals.push([start, end]);
    }
    intervals.sort((a, b) => a[0] - b[0]);

    const color = "rgba(226, 232, 240, 0.35)";
    const stops = [];
    let pos = 0;
    for (const [start, end] of intervals) {
      if (start > pos) {
        stops.push(`${color} ${pos}px`, `${color} ${start}px`);
      }
      stops.push(
        `transparent ${Math.max(pos, start)}px`,
        `transparent ${end}px`
      );
      pos = Math.max(pos, end);
    }
    stops.push(`${color} ${pos}px`, `${color} ${height}px`);

    line.style.display = "block";
    line.style.left = `${x - containerRect.left}px`;
    line.style.top = `${topY - containerRect.top}px`;
    line.style.height = `${height}px`;
    line.style.background = `linear-gradient(to bottom, ${stops.join(", ")})`;
  }

  /**
   * Position the parents -> ego and couple -> descendants lines. Their
   * lengths depend on layout (wrapped rows may put other boxes in between),
   * so they are measured from the rendered boxes: the upper line is anchored
   * on the ego chip, the lower one on the descendants box.
   */
  function updateFamilyLinks() {
    if (!familyGenerationsEl) return;
    const containerRect = familyGenerationsEl.getBoundingClientRect();
    const egoBox = familyGenerationsEl.querySelector(".family-box.ego-box");

    const egoLine = familyGenerationsEl.querySelector(
      '.family-link-line[data-link="ego"]'
    );
    if (egoLine) {
      const chip = familyGenerationsEl.querySelector(".ego-chip.link-up");
      const sourceBox = familyGenerationsEl.querySelector(
        ".family-box.link-source"
      );
      if (chip && sourceBox) {
        const chipRect = chip.getBoundingClientRect();
        const sourceRect = sourceBox.getBoundingClientRect();
        drawVerticalLink(
          egoLine,
          containerRect,
          chipRect.left + chipRect.width / 2,
          sourceRect.bottom,
          chipRect.top,
          [sourceBox, egoBox]
        );
      } else {
        egoLine.style.display = "none";
      }
    }

    const childLine = familyGenerationsEl.querySelector(
      '.family-link-line[data-link="children"]'
    );
    if (childLine) {
      const targetBox = familyGenerationsEl.querySelector(
        ".family-box.link-target"
      );
      if (targetBox && egoBox) {
        const targetRect = targetBox.getBoundingClientRect();
        const egoRect = egoBox.getBoundingClientRect();
        drawVerticalLink(
          childLine,
          containerRect,
          targetRect.left + targetRect.width / 2,
          egoRect.bottom,
          targetRect.top,
          [egoBox, targetBox]
        );
      } else {
        childLine.style.display = "none";
      }
    }
  }

  let resizeObserver = null;
  let observedEl = null;

  onMount(() => {
    resizeObserver = new ResizeObserver(() => updateFamilyLinks());
    window.addEventListener("resize", updateFamilyLinks);
    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", updateFamilyLinks);
    };
  });

  afterUpdate(() => {
    if (familyGenerationsEl !== observedEl) {
      if (observedEl) resizeObserver?.unobserve(observedEl);
      if (familyGenerationsEl) resizeObserver?.observe(familyGenerationsEl);
      observedEl = familyGenerationsEl;
    }
    updateFamilyLinks();
  });

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
<div data-dialog-overlay class="modal-overlay" on:click={onClose}>
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    class="network-modal"
    style={storyStyleVars(styleConfig)}
    on:click|stopPropagation
    use:dialog={{ onClose, initialFocus: ".close-button" }}
    role="dialog"
    aria-modal="true"
    aria-labelledby="network-modal-title"
    tabindex="-1"
  >
    <div class="modal-header">
      <h3 id="network-modal-title" class="modal-title">
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
      }) as [type, people] (type)}
        {#if type === "family"}
          {@const familyGenerations = buildFamilyGenerations(people)}
          <div class="person-group">
            <h4 class="group-title">
              {relationshipCategoryLabel($_, type, people.length)}
              <span class="group-count"
                >{$_("network.group_count", { count: people.length })}</span
              >
            </h4>
            <div class="group-layout">
              <div class="group-description">
                {#if summaryMap[type]}
                  {@const summarySegments = parseTextWithPeople(
                    summaryMap[type],
                    people
                  )}
                  <p class="category-summary">
                    {#each summarySegments as segment}{#if segment.type === "text"}{segment.content}{:else}<strong
                          class="person-mention">{segment.content}</strong
                        >{/if}{/each}
                  </p>
                {/if}
              </div>

              <div class="group-connections">
                <div class="family-generations" bind:this={familyGenerationsEl}>
                  <div class="family-link-line" data-link="ego"></div>
                  <div class="family-link-line" data-link="children"></div>
                  {#each familyGenerations.rows as row (row.layer)}
                    <div class="generation-row">
                      {#each row.boxes as box (box.id)}
                        <div
                          class="family-box"
                          class:ego-box={box.isEgo}
                          class:link-up-box={box.linkUpBox}
                          class:link-down-box={box.linkDownBox}
                          class:link-source={box.linkSource}
                          class:link-target={box.linkTarget}
                        >
                          {#if box.labelKey}
                            <span class="family-box-label"
                              >{$_(
                                box.people.length === 1
                                  ? `${box.labelKey}_one`
                                  : `${box.labelKey}_other`
                              )}</span
                            >
                          {:else}
                            <!-- blank line keeps box heights aligned -->
                            <span class="family-box-label">&nbsp;</span>
                          {/if}
                          <div class="family-box-people">
                            {#if box.isEgo}
                              <div
                                class="ego-chip"
                                class:link-up={box.linkUp}
                                title={personName}
                              >
                                {#if portrait?.thumbnail || portrait?.image}
                                  <span class="ego-portrait-clip">
                                    <img
                                      class="ego-portrait"
                                      src={assetUrl(
                                        portrait.thumbnail || portrait.image
                                      )}
                                      alt={personName}
                                    />
                                  </span>
                                {:else}
                                  <svg
                                    class="ego-icon"
                                    viewBox="0 0 24 24"
                                    role="img"
                                    aria-label={personName}
                                  >
                                    <path d={mdiAccount} />
                                  </svg>
                                {/if}
                              </div>
                            {/if}
                            {#each box.people as person, idx (person.person_name)}
                              <PersonChip
                                {person}
                                personKey={`family-${box.id}-${idx}`}
                                {visiblePersonInfo}
                                subcategory={getSubcategory(
                                  person.relationship_type
                                )}
                                {styleConfig}
                                stacked
                                onToggle={togglePersonInfo}
                                containerSelector=".modal-content"
                              />
                            {/each}
                          </div>
                        </div>
                      {/each}
                    </div>
                  {/each}

                  {#if familyGenerations.other.length > 0}
                    <div class="generation-row other-row">
                      <div class="family-box other-box">
                        <span class="family-box-label"
                          >{$_(
                            familyGenerations.other.length === 1
                              ? "network.family.other_one"
                              : "network.family.other_other"
                          )}</span
                        >
                        <div class="family-box-people">
                          {#each familyGenerations.other as person, idx (person.person_name)}
                            <PersonChip
                              {person}
                              personKey={`family-other-${idx}`}
                              {visiblePersonInfo}
                              subcategory={getSubcategory(
                                person.relationship_type
                              )}
                              {styleConfig}
                              stacked
                              onToggle={togglePersonInfo}
                              containerSelector=".modal-content"
                            />
                          {/each}
                        </div>
                      </div>
                    </div>
                  {/if}
                </div>
              </div>
            </div>
          </div>
        {:else}
          {@const subgroups = groupBySubcategory(people)}
          <div class="person-group">
            <h4 class="group-title">
              {relationshipCategoryLabel($_, type, people.length)}
              <span class="group-count"
                >{$_("network.group_count", { count: people.length })}</span
              >
            </h4>
            <div class="group-layout">
              <div class="group-description">
                {#if summaryMap[type]}
                  {@const summarySegments = parseTextWithPeople(
                    summaryMap[type],
                    people
                  )}
                  <p class="category-summary">
                    {#each summarySegments as segment}{#if segment.type === "text"}{segment.content}{:else}<strong
                          class="person-mention">{segment.content}</strong
                        >{/if}{/each}
                  </p>
                {/if}
              </div>

              <div class="group-connections">
                <div class="generation-row">
                  {#each subgroups as subgroup (subgroup.subcategory ?? "other")}
                    {@const boxLabel =
                      subgroup.label ??
                      (subgroup.isOther ? $_("network.other") : null)}
                    <div class="family-box" class:other-box={subgroup.isOther}>
                      {#if boxLabel}
                        <span class="family-box-label">{boxLabel}</span>
                      {/if}
                      <div class="family-box-people">
                        {#each subgroup.people as person, idx (person.person_name)}
                          <PersonChip
                            {person}
                            personKey={`${type}-${subgroup.subcategory || "default"}-${idx}`}
                            {visiblePersonInfo}
                            subcategory={getSubcategory(
                              person.relationship_type
                            )}
                            {styleConfig}
                            stacked
                            showRole={!subgroup.subcategory}
                            onToggle={togglePersonInfo}
                            containerSelector=".modal-content"
                          />
                        {/each}
                      </div>
                    </div>
                  {/each}
                </div>
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

  /* Family generation layout: three stacked layers of grouped boxes.
     The row/box classes are shared with the other relationship categories. */
  .family-generations {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.1rem;
  }

  /* Parents -> ego and couple -> descendants lines;
     positioned and colored by updateFamilyLinks() */
  .family-link-line {
    position: absolute;
    z-index: -1;
    display: none;
    width: 1px;
    pointer-events: none;
  }

  .generation-row {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    align-items: stretch;
    gap: 0.6rem;
    width: 100%;
  }

  .family-box {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.45rem;
    padding: 0.5rem 0.6rem 0.6rem;
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 0.75rem;
    background: rgba(148, 163, 184, 0.06);
    min-width: 0;
  }

  .family-box.ego-box {
    border-color: rgba(148, 163, 184, 0.55);
    background: rgba(148, 163, 184, 0.1);
    border-color: color-mix(
      in srgb,
      var(--story-secondary, #38bdf8) 55%,
      transparent
    );
    background: color-mix(
      in srgb,
      var(--story-secondary, #38bdf8) 8%,
      transparent
    );
  }

  /* Box-to-box link upward (e.g. siblings to their shared parents) */
  .family-box.link-up-box::before {
    content: "";
    position: absolute;
    z-index: -1;
    bottom: 100%;
    left: 50%;
    width: 1px;
    height: 1.1rem;
    background: linear-gradient(
      to top,
      rgba(226, 232, 240, 0.45),
      rgba(226, 232, 240, 0.15)
    );
  }

  /* Box-to-box link downward (e.g. grandparents to the parents' generation) */
  .family-box.link-down-box::after {
    content: "";
    position: absolute;
    z-index: -1;
    top: 100%;
    left: 50%;
    width: 1px;
    height: 1.1rem;
    background: linear-gradient(
      to bottom,
      rgba(226, 232, 240, 0.45),
      rgba(226, 232, 240, 0.15)
    );
  }

  .family-box.other-box {
    border-style: dashed;
  }

  .family-box-label {
    font-size: 0.62rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: rgba(226, 232, 240, 0.75);
    font-family: var(--story-body-font, Inter, sans-serif);
    line-height: 1;
  }

  .family-box-people {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    align-items: stretch;
    gap: 0.4rem;
  }

  /* Ego chip: non-interactive portrait marker for the central person,
     styled like the meta timeline portraits */
  .ego-chip {
    position: relative;
    display: inline-flex;
    justify-content: center;
    align-items: center;
    align-self: center;
    width: 44px;
    height: 44px;
    flex: 0 0 auto;
    border: 2px solid rgba(226, 232, 240, 0.65);
    border-color: color-mix(
      in srgb,
      var(--story-primary, #f8fafc) 80%,
      transparent
    );
    border-radius: 50%;
    background: rgba(15, 23, 42, 0.9);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
    box-sizing: border-box;
  }

  /* Clips the zoomed portrait without clipping the .link-up line above */
  .ego-portrait-clip {
    position: absolute;
    inset: 0;
    display: block;
    border-radius: 50%;
    overflow: hidden;
  }

  .ego-portrait {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center 35%;
    scale: 1.25;
  }

  .ego-icon {
    width: 1.3rem;
    height: 1.3rem;
    fill: var(--story-primary, #f8fafc);
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

    /* Two-column layout for wider screens: description 30%, connections 60% */
    .group-layout {
      display: grid;
      grid-template-columns: 3fr 6fr;
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
