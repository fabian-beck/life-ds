<script>
  import { onMount, onDestroy, tick } from "svelte";
  import {
    forceSimulation,
    forceManyBody,
    forceLink,
    forceCollide,
    forceX,
    forceY,
  } from "d3-force";
  import { _ } from "../stores/language.js";
  import { displayName } from "../utils/helpers.js";
  import { computeClusters } from "../utils/networkClusters.js";
  import { generateNameVariants } from "../utils/storyHelpers.js";
  import { saveMetaStoryScroll } from "../stores/metaStoryScroll.js";
  import personStylesData from "../../data/person_styles.json";

  // The `social_network` block from a meta story: { nodes: [...], links: [...] }
  export let network = null;
  export let currentLanguage = "en";
  // Id of the meta story this network belongs to, so opening a person's story
  // carries the `from_meta` context (returning restores the meta story + scroll).
  export let metaStoryId = null;

  const personStyles = personStylesData.styles;

  const SECONDARY_COLOR = "#94a3b8";
  const LINK_IDLE = "#64748b"; // links when nothing is focused
  const LINK_ACTIVE = "#38bdf8"; // focused ties (meta accent)
  const LINK_MUTED = "#475569"; // other ties while something is focused

  // How many ties a cluster card spells out before summarizing the rest.
  const MAX_CARD_TIES = 4;

  // Person primary color from the shared style registry (matches the timeline).
  function primaryColor(personId) {
    return personStyles[personId]?.primary || "#38bdf8";
  }

  // Links carry no colour meaning on their own: they read as neutral until a
  // node is hovered/tapped or a cluster card is in view, then the focused ties
  // light up in the accent colour while the rest recede.
  function linkState(link, aId, cIds) {
    if (aId != null) {
      return link.source === aId || link.target === aId ? "active" : "muted";
    }
    if (cIds) {
      return cIds.has(link.source) && cIds.has(link.target)
        ? "active"
        : "muted";
    }
    return "idle";
  }
  function linkStroke(link, aId, cIds) {
    const s = linkState(link, aId, cIds);
    return s === "idle" ? LINK_IDLE : s === "active" ? LINK_ACTIVE : LINK_MUTED;
  }
  function linkOpacity(link, aId, cIds) {
    const s = linkState(link, aId, cIds);
    const sec = link.kind === "secondary";
    if (s === "idle") return sec ? 0.5 : 0.75;
    if (s === "active") return sec ? 0.75 : 0.95;
    return 0.12;
  }
  // Main links encode tie strength through width; secondary ties stay thin.
  function linkWidth(link) {
    if (link.kind === "secondary") return 1.5;
    return link.strength === "strong"
      ? 3.5
      : link.strength === "weak"
        ? 1.5
        : 2.5;
  }

  // Humanize a relationship_type: "professional/mentor" → "Professional · Mentor".
  function humanizeRelationship(relationshipType) {
    if (!relationshipType) return "";
    return relationshipType
      .split("/")
      .map((part) =>
        part
          .replace(/[_-]+/g, " ")
          .replace(/\b\w/g, (c) => c.toUpperCase())
          .trim()
      )
      .filter(Boolean)
      .join(" · ");
  }

  // --- Layout / simulation state -------------------------------------------
  let container;
  let width = 0;

  // Responsive sizing: smaller nodes and a taller frame on narrow screens so a
  // crowded cast still fits without overlap. Declared before the build reactive
  // block so these run first when the width becomes known.
  $: compact = width > 0 && width < 560;
  $: MAIN_R = compact ? 23 : 30;
  $: SECONDARY_R = compact ? 9 : 11;
  $: height = compact ? 640 : 520;
  $: insetX = compact ? 62 : 82;

  let simulation = null;
  let simNodes = [];
  let simLinks = [];
  let simBuilt = false;
  let builtWidth = 0; // width the current layout was computed for
  let ready = false; // becomes true once the background layout has settled
  let rafId = 0; // requestAnimationFrame handle for the background layout
  let hoveredId = null; // transient (pointer over a node)
  let selectedId = null; // pinned by tap/click (persists, mobile-friendly)

  // The node whose ties are highlighted: hover wins, else pin.
  $: activeId = hoveredId ?? selectedId;

  // A tapped/clicked MAIN node opens a compact popup offering to jump to that
  // person's own story. Secondary (bridging) nodes have no story, so no popup.
  $: selectedNode = selectedId != null ? posById.get(selectedId) : null;
  $: popupNode =
    selectedNode && selectedNode.type === "main" ? selectedNode : null;
  // Prefer above the node; flip below when it would clip the frame's top.
  $: popupAbove = popupNode ? popupNode.y - MAIN_R > 96 : true;
  // Keep the popup fully inside the (overflow-clipped) frame, then aim its
  // little tail back at the node it belongs to.
  $: popupHalf = compact ? 92 : 112;
  $: popupCx = popupNode
    ? Math.min(Math.max(popupNode.x, popupHalf + 6), width - popupHalf - 6)
    : 0;
  $: popupTailDx = popupNode ? popupNode.x - popupCx : 0;
  // Carry the meta story context so the story's close button returns here.
  $: popupHref = popupNode
    ? `#/${currentLanguage}/story/${popupNode.id}` +
      (metaStoryId ? `?from_meta=${metaStoryId}` : "")
    : "#";

  // Remember where the reader left the meta story before jumping into a story.
  function openStory() {
    if (metaStoryId) saveMetaStoryScroll(metaStoryId);
  }

  // Rendered node positions resolved by id (kept in sync with the simulation on
  // every tick). Links read positions from here rather than from d3's mutated
  // link.source/target objects, so endpoints always match the drawn nodes.
  $: posById = new Map(simNodes.map((n) => [n.id, n]));

  // IDs of nodes adjacent to the active node (for highlight/dimming).
  $: neighborIds = (() => {
    const set = new Set();
    if (activeId == null) return set;
    set.add(activeId);
    for (const l of simLinks) {
      if (l.source === activeId) set.add(l.target);
      if (l.target === activeId) set.add(l.source);
    }
    return set;
  })();

  $: hasNetwork =
    network &&
    Array.isArray(network.nodes) &&
    network.nodes.length > 0 &&
    Array.isArray(network.links) &&
    network.links.length > 0;

  // --- Scroll narration ("circles") ----------------------------------------
  // Clusters derived from the network, ordered roughly by time. Each gets a
  // card that scrolls over the pinned graph and highlights its members.
  $: clusters = hasNetwork ? computeClusters(network) : [];
  $: nodeById = new Map(hasNetwork ? network.nodes.map((n) => [n.id, n]) : []);

  // Story texts authored by the generation pipeline (social_network.narration),
  // matched to clusters by key. A card shows its cluster's story text; only
  // when a text is missing (e.g. clusters changed since narration was written)
  // does it fall back to listing the ties.
  $: narrationTexts = new Map(
    (network?.narration?.circles || []).map((c) => [c.key, c.text])
  );
  // AI-written headline per circle (social_network.narration). When absent
  // (older data), the card falls back to a joined list of the members' names.
  $: narrationTitles = new Map(
    (network?.narration?.circles || [])
      .filter((c) => c.title)
      .map((c) => [c.key, c.title])
  );

  // Highlight each circle member's name where it appears in the narration text,
  // the way person names are emphasized in the story slides. Returns an array
  // of { type: "text" | "person", content, personType, personId } segments.
  function highlightNarration(text, cluster) {
    if (!text) return [{ type: "text", content: "" }];
    const people = [...cluster.mains, ...cluster.secondaries];

    // Best (longest / highest-priority) match per person.
    const matches = [];
    for (const person of people) {
      let best = null;
      for (const variant of generateNameVariants(person.name)) {
        variant.regex.lastIndex = 0;
        let m;
        while ((m = variant.regex.exec(text)) !== null) {
          const cand = {
            start: m.index,
            end: variant.regex.lastIndex,
            len: m[0].length,
            priority: variant.priority,
            person,
          };
          if (
            !best ||
            cand.priority < best.priority ||
            (cand.priority === best.priority && cand.len > best.len)
          ) {
            best = cand;
          }
        }
      }
      if (best) matches.push(best);
    }

    // Resolve overlaps: earliest start wins, then the longer span.
    matches.sort((a, b) => a.start - b.start || b.len - a.len);
    const segments = [];
    let cursor = 0;
    for (const match of matches) {
      if (match.start < cursor) continue; // overlaps a chosen match — skip
      if (match.start > cursor) {
        segments.push({
          type: "text",
          content: text.slice(cursor, match.start),
        });
      }
      segments.push({
        type: "person",
        content: text.slice(match.start, match.end),
        personType: match.person.type,
        personId: match.person.id,
      });
      cursor = match.end;
    }
    if (cursor < text.length) {
      segments.push({ type: "text", content: text.slice(cursor) });
    }
    return segments;
  }

  // Which step card is in the viewport band; each step maps 1:1 to a cluster.
  let activeStep = null;
  $: scrollCluster = activeStep != null ? (clusters[activeStep] ?? null) : null;
  // Node-level focus (hover/tap) temporarily overrides the cluster highlight.
  $: clusterIds =
    activeId == null && scrollCluster ? scrollCluster.nodeIds : null;

  // A pinned node selection would block the narration once the reader scrolls
  // on, so moving to another card releases it.
  let lastStep = null;
  $: if (activeStep !== lastStep) {
    lastStep = activeStep;
    selectedId = null;
  }

  function isDimmed(nodeId, aId, nIds, cIds) {
    if (aId != null) return !nIds.has(nodeId);
    if (cIds) return !cIds.has(nodeId);
    return false;
  }

  // A step activates while its card crosses the lower third of the viewport,
  // so the highlight is readable before the card covers the graph, and stays
  // active until the next card takes over. The observer only says WHEN to look
  // (a card crossed the band); the active step is recomputed from the cards'
  // actual positions, so jump-scrolls (scrollbar drags) can't leave a stale
  // highlight behind.
  const BAND_BOTTOM = 0.75; // matches the observer's -25% bottom rootMargin
  const stepEls = [];
  let stepObserver = null;

  function recomputeActiveStep() {
    const bandBottom = window.innerHeight * BAND_BOTTOM;
    let current = null;
    for (let i = 0; i < stepEls.length; i++) {
      const el = stepEls[i];
      if (el && el.getBoundingClientRect().top < bandBottom) current = i;
    }
    activeStep = current;
  }

  function observeStep(node, index) {
    if (!stepObserver && typeof IntersectionObserver !== "undefined") {
      stepObserver = new IntersectionObserver(recomputeActiveStep, {
        rootMargin: "-55% 0px -25% 0px",
      });
    }
    stepEls[index] = node;
    stepObserver?.observe(node);
    return {
      destroy() {
        stepObserver?.unobserve(node);
        if (stepEls[index] === node) stepEls[index] = null;
      },
    };
  }

  // "Ada Lovelace, Charles Babbage and Konrad Zuse" — localized list joining.
  function formatNameList(names, lang) {
    try {
      return new Intl.ListFormat(lang, {
        style: "long",
        type: "conjunction",
      }).format(names);
    } catch {
      return names.join(", ");
    }
  }

  function clusterTitle(cluster, lang) {
    return formatNameList(
      cluster.mains.map((n) => displayName(n.name)),
      lang
    );
  }

  // Card tie label with the story's own person first: "Ada Lovelace · Mary Somerville".
  function tieNames(link) {
    const a = nodeById.get(link.source);
    const b = nodeById.get(link.target);
    const [first, second] =
      a?.type !== "main" && b?.type === "main" ? [b, a] : [a, b];
    return `${displayName(first?.name || link.source)} · ${displayName(
      second?.name || link.target
    )}`;
  }

  // Temporal layout: assign each node a target x from its birth year so the
  // graph reads left→right in chronological order. Main nodes map their birth
  // year across the frame; secondary (bridging) nodes, which have no birth year,
  // sit at the mean x of the main people they connect.
  function computeTargets(w) {
    const years = simNodes
      .filter((n) => n.type === "main" && n.birth_year)
      .map((n) => n.birth_year);
    const left = insetX;
    const right = w - insetX;
    const minY = years.length ? Math.min(...years) : 0;
    const maxY = years.length ? Math.max(...years) : 0;
    const scaleX = (y) =>
      maxY === minY
        ? w / 2
        : left + ((y - minY) / (maxY - minY)) * (right - left);

    for (const n of simNodes) {
      n.tx = n.type === "main" && n.birth_year ? scaleX(n.birth_year) : null;
    }
    const byId = new Map(simNodes.map((n) => [n.id, n]));
    for (const n of simNodes) {
      if (n.tx != null) continue;
      const xs = [];
      for (const l of simLinks) {
        const otherId =
          l.source === n.id ? l.target : l.target === n.id ? l.source : null;
        const other = otherId && byId.get(otherId);
        if (other && other.tx != null) xs.push(other.tx);
      }
      n.tx = xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : w / 2;
    }
  }

  function buildSimulation() {
    if (!hasNetwork || !width) return;

    // Fresh copies so d3's in-place mutation never touches the prop data.
    simNodes = network.nodes.map((n) => ({ ...n }));
    const nodeIds = new Set(simNodes.map((n) => n.id));
    const valid = network.links.filter(
      (l) => nodeIds.has(l.source) && nodeIds.has(l.target)
    );
    // `simLinks` (for rendering) keeps string ids and metadata. d3 gets its own
    // array, which it mutates by replacing source/target with node objects.
    simLinks = valid.map((l) => ({ ...l }));
    const forceLinks = valid.map((l) => ({
      source: l.source,
      target: l.target,
      kind: l.kind,
    }));

    // Seed positions in temporal order so the layout settles left→right.
    computeTargets(width);
    for (const n of simNodes) {
      n.x = n.tx;
      n.y = height / 2 + (Math.random() - 0.5) * height * 0.5;
    }

    if (simulation) simulation.stop();

    // Create the simulation STOPPED — the layout is computed off the render path
    // (see runLayout) so the graph never animates on its own.
    simulation = forceSimulation(simNodes)
      .stop()
      .force(
        "link",
        forceLink(forceLinks)
          .id((d) => d.id)
          .distance((l) => (l.kind === "secondary" ? 70 : 130))
          .strength((l) => (l.kind === "secondary" ? 0.35 : 0.12))
      )
      .force(
        "charge",
        forceManyBody().strength((d) => (d.type === "main" ? -520 : -160))
      )
      // Weak temporal pull toward each node's birth-year x (left→right).
      .force("x", forceX((d) => d.tx).strength(0.14))
      .force("y", forceY(height / 2).strength(0.06))
      // Extra collide iterations space nodes (and their labels) apart cleanly.
      .force(
        "collide",
        forceCollide()
          .radius((d) => (d.type === "main" ? MAIN_R + 26 : SECONDARY_R + 16))
          .strength(1)
          .iterations(3)
      );

    runLayout();
    builtWidth = width;
    simBuilt = true;
  }

  // Compute the layout in the BACKGROUND: advance the simulation to full
  // convergence in per-frame batches (so the main thread is never blocked and
  // it isn't rushed), keeping it hidden behind a placeholder, then reveal the
  // finished, static layout. Nothing is rendered until it is ready.
  function runLayout() {
    if (!simulation) return;
    if (rafId) cancelAnimationFrame(rafId);
    ready = false;
    simulation.alpha(1).alphaDecay(0.0228); // default decay → ~300 iterations
    const alphaMin = simulation.alphaMin();
    const step = () => {
      // ~18 ticks per frame settles a graph in a few hundred ms without jank.
      for (let i = 0; i < 18 && simulation.alpha() >= alphaMin; i++) {
        simulation.tick();
      }
      clampNodes();
      if (simulation.alpha() < alphaMin) {
        rafId = 0;
        ready = true;
        simNodes = simNodes; // single render with the final positions
      } else {
        rafId = requestAnimationFrame(step);
      }
    };
    rafId = requestAnimationFrame(step);
  }

  // Keep nodes (and their labels) within the frame. The horizontal inset
  // reserves room for the label text centered under each node; the top strip
  // keeps nodes and their upper halo clear of the frame edge.
  function clampNodes() {
    for (const n of simNodes) {
      const r = n.type === "main" ? MAIN_R : SECONDARY_R;
      const ix = n.type === "main" ? insetX : insetX - 22;
      n.x = Math.max(ix, Math.min(width - ix, n.x));
      n.y = Math.max(r + 40, Math.min(height - r - 24, n.y));
    }
  }

  // Rebuild once the width is known; rebuild again when the story changes.
  $: (network, (simBuilt = false));
  $: if (hasNetwork && width && !simBuilt) {
    buildSimulation();
  }

  // --- Selection (tap / click) ---------------------------------------------
  // Nodes are not draggable; tapping one pins its ties highlighted.
  function selectNode(node, evt) {
    evt.stopPropagation();
    selectedId = selectedId === node.id ? null : node.id;
  }

  // Clicking empty canvas clears the selection (node clicks stopPropagation).
  function clearSelection() {
    selectedId = null;
  }

  function clipId(nodeId) {
    return "mnet-clip-" + nodeId.replace(/[^a-zA-Z0-9_-]/g, "_");
  }

  onMount(() => {
    if (container) width = container.clientWidth;
  });

  onDestroy(() => {
    if (rafId) cancelAnimationFrame(rafId);
    if (simulation) simulation.stop();
    stepObserver?.disconnect();
  });

  async function handleResize() {
    if (!container || !simulation) return;
    const w = container.clientWidth;
    // Ignore resizes that don't change the width (e.g. the mobile URL bar
    // showing/hiding during a scroll) — those must not disturb the layout.
    if (w === builtWidth) return;
    width = w;
    await tick(); // let compact/insetX/height react to the new width
    computeTargets(width);
    simulation.force("y", forceY(height / 2).strength(0.06));
    // Recompute the layout in the background (hidden), then reveal.
    runLayout();
    builtWidth = width;
  }
</script>

<svelte:window on:resize={handleResize} />

{#if hasNetwork}
  <div class="mnet">
    <!-- The graph pins below the sticky header while the cards scroll over it -->
    <div class="mnet-sticky">
      <div
        class="network-frame"
        bind:this={container}
        bind:clientWidth={width}
        style="height: {height}px;"
      >
        {#if !ready}
          <div class="network-loading">{$_("meta_story.network_loading")}</div>
        {/if}
        <svg
          class="network-svg"
          class:hidden={!ready}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={$_("meta_story.network_aria")}
          on:pointerup={clearSelection}
        >
          <defs>
            {#each simNodes as node (node.id)}
              {#if node.type === "main" && node.portrait}
                <clipPath id={clipId(node.id)}>
                  <circle cx="0" cy="0" r={MAIN_R} />
                </clipPath>
              {/if}
            {/each}
          </defs>

          <!-- Links -->
          <g class="links" stroke-linecap="round">
            {#each simLinks as link (`${link.source}-${link.target}`)}
              {@const s = posById.get(link.source)}
              {@const t = posById.get(link.target)}
              {#if s && t}
                <line
                  x1={s.x}
                  y1={s.y}
                  x2={t.x}
                  y2={t.y}
                  stroke={linkStroke(link, activeId, clusterIds)}
                  stroke-width={linkWidth(link)}
                  stroke-dasharray={link.kind === "secondary" ? "5 4" : null}
                  opacity={linkOpacity(link, activeId, clusterIds)}
                >
                  <title
                    >{humanizeRelationship(
                      link.relationship_type
                    )}{link.relationship_description
                      ? " — " + link.relationship_description
                      : ""}</title
                  >
                </line>
              {/if}
            {/each}
          </g>

          <!-- Nodes -->
          <g class="nodes">
            {#each simNodes as node (node.id)}
              {@const dim = isDimmed(
                node.id,
                activeId,
                neighborIds,
                clusterIds
              )}
              <g
                class="node"
                class:main={node.type === "main"}
                class:secondary={node.type === "secondary"}
                class:dim
                class:selected={node.id === selectedId}
                transform={`translate(${node.x ?? width / 2}, ${node.y ?? height / 2})`}
                on:pointerup={(e) => selectNode(node, e)}
                on:pointerenter={() => (hoveredId = node.id)}
                on:pointerleave={() => (hoveredId = null)}
                role="listitem"
              >
                <title
                  >{node.name}{node.roles && node.roles.length
                    ? " — " + node.roles.join(", ")
                    : ""}</title
                >

                {#if node.type === "main"}
                  <circle
                    class="halo"
                    r={MAIN_R + 3}
                    fill="none"
                    stroke={primaryColor(node.id)}
                    stroke-width={node.id === selectedId ? 4.5 : 3}
                  />
                  {#if node.portrait}
                    <image
                      href={node.portrait}
                      x={-MAIN_R}
                      y={-MAIN_R}
                      width={MAIN_R * 2}
                      height={MAIN_R * 2}
                      clip-path={`url(#${clipId(node.id)})`}
                      preserveAspectRatio="xMidYMid slice"
                    />
                  {:else}
                    <circle
                      r={MAIN_R}
                      fill={primaryColor(node.id)}
                      opacity="0.35"
                    />
                  {/if}
                  <text class="label main-label" y={MAIN_R + 16}>
                    {displayName(node.name)}
                  </text>
                {:else}
                  <circle
                    r={SECONDARY_R}
                    fill="#1e293b"
                    stroke={SECONDARY_COLOR}
                    stroke-width="1.5"
                  />
                  <text class="label secondary-label" y={SECONDARY_R + 13}>
                    {displayName(node.name)}
                  </text>
                {/if}
              </g>
            {/each}
          </g>
        </svg>

        {#if ready && popupNode}
          <div
            class="node-popup"
            class:below={!popupAbove}
            style="left: {popupCx}px; top: {popupAbove
              ? popupNode.y - MAIN_R - 10
              : popupNode.y + MAIN_R + 10}px; --tail-dx: {popupTailDx}px;"
          >
            <span class="node-popup-name">{displayName(popupNode.name)}</span>
            <a class="node-popup-link" href={popupHref} on:click={openStory}>
              {$_("meta_story.network_open_story")}
              <span aria-hidden="true">→</span>
            </a>
          </div>
        {/if}
      </div>
    </div>

    <!-- Narration: cards scroll up over the pinned graph, each highlighting
         and explaining one circle of connected people. -->
    {#if clusters.length}
      <ol class="mnet-steps">
        {#each clusters as cluster, i (cluster.key)}
          <li class="step" use:observeStep={i}>
            <div class="step-card" class:current={activeStep === i}>
              <p class="step-kicker">
                {$_("meta_story.network_step", {
                  index: i + 1,
                  total: clusters.length,
                })}
              </p>
              <h3 class="step-title">
                {narrationTitles.get(cluster.key) ??
                  clusterTitle(cluster, currentLanguage)}
              </h3>
              {#if narrationTexts.has(cluster.key)}
                <p class="step-body">
                  {#each highlightNarration(narrationTexts.get(cluster.key), cluster) as seg}{#if seg.type === "text"}{seg.content}{:else if seg.personType === "main"}<strong
                        class="person-mention"
                        style={`--mention-color: ${primaryColor(seg.personId)}`}
                        >{seg.content}</strong
                      >{:else}<strong
                        class="person-mention person-mention-secondary"
                        >{seg.content}</strong
                      >{/if}{/each}
                </p>
              {:else}
                <ul class="tie-list">
                  {#each cluster.links.slice(0, MAX_CARD_TIES) as tie (`${tie.source}-${tie.target}`)}
                    <li
                      class="tie"
                      class:is-secondary={tie.kind === "secondary"}
                    >
                      <div class="tie-head">
                        <span class="tie-names">{tieNames(tie)}</span>
                        {#if tie.relationship_type}
                          <span class="tie-rel"
                            >{humanizeRelationship(tie.relationship_type)}</span
                          >
                        {/if}
                      </div>
                      {#if tie.relationship_description}
                        <p class="tie-desc">{tie.relationship_description}</p>
                      {/if}
                    </li>
                  {/each}
                </ul>
                {#if cluster.links.length > MAX_CARD_TIES}
                  <p class="tie-more">
                    {$_("meta_story.network_more_ties", {
                      count: cluster.links.length - MAX_CARD_TIES,
                    })}
                  </p>
                {/if}
              {/if}
            </div>
          </li>
        {/each}
      </ol>
    {/if}
  </div>
{/if}

<style>
  .mnet {
    position: relative;
  }

  /* The graph sticks below the app's sticky header while the narration cards
     (which follow in flow) scroll up and over it. */
  .mnet-sticky {
    position: sticky;
    top: calc(var(--sticky-header-height, 0px) + 0.5rem);
    z-index: 1;
  }

  .network-frame {
    position: relative;
    width: 100%;
    /* Embedded look: no card border, just a soft glow so it blends into the
       story page rather than reading as a separate widget. */
    background: radial-gradient(
      circle at 50% 30%,
      rgba(56, 189, 248, 0.05),
      transparent 65%
    );
    overflow: hidden;
    /* Allow vertical page scrolling to pass through the graph area on touch;
       nodes opt back out (touch-action: none) so dragging still works. */
    touch-action: pan-y;
  }

  .network-svg {
    display: block;
    width: 100%;
    height: 100%;
    opacity: 1;
    transition: opacity 0.3s ease;
  }
  /* Kept mounted (so clip paths and pointer handlers persist) but invisible
     until the background layout has settled. */
  .network-svg.hidden {
    opacity: 0;
    pointer-events: none;
  }

  .network-loading {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #94a3b8;
    font-size: 0.9rem;
    letter-spacing: 0.01em;
    animation: mnet-pulse 1.4s ease-in-out infinite;
  }

  @keyframes mnet-pulse {
    0%,
    100% {
      opacity: 0.55;
    }
    50% {
      opacity: 1;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .network-svg {
      transition: none;
    }
    .network-loading {
      animation: none;
    }
    .node {
      transition: none;
    }
    .node-popup {
      animation: none;
    }
  }

  .node {
    cursor: pointer;
    transition: filter 0.18s ease;
  }

  /* Blend out non-focused nodes by DARKENING them (kept fully opaque) so the
     links that sit behind them do not shine through. */
  .node.dim {
    filter: brightness(0.32) saturate(0.5);
  }

  .halo {
    filter: drop-shadow(0 0 6px rgba(56, 189, 248, 0.35));
  }

  .node.selected .halo {
    filter: drop-shadow(0 0 9px rgba(56, 189, 248, 0.6));
  }

  .label {
    text-anchor: middle;
    fill: #e2e8f0;
    font-family: var(--heading-font, "Space Grotesk", sans-serif);
    pointer-events: none;
    paint-order: stroke;
    stroke: rgba(2, 6, 23, 0.85);
    stroke-width: 3px;
    stroke-linejoin: round;
  }

  .main-label {
    font-size: 13px;
    font-weight: 600;
  }

  .secondary-label {
    font-size: 10.5px;
    font-weight: 500;
    fill: #cbd5e1;
  }

  /* --- Node popup (tap/click a person to open their story) ---------------- */
  .node-popup {
    position: absolute;
    z-index: 4;
    transform: translate(-50%, -100%);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.3rem;
    padding: 0.5rem 0.7rem;
    background: rgba(15, 23, 42, 0.94);
    border: 1px solid rgba(56, 189, 248, 0.45);
    border-radius: 10px;
    box-shadow: 0 8px 24px rgba(2, 6, 23, 0.55);
    text-align: center;
    white-space: nowrap;
    pointer-events: auto;
    animation: mnet-pop 0.14s ease-out;
  }

  .node-popup.below {
    transform: translate(-50%, 0);
  }

  /* Little tail aimed back at the node (shifted when the card was clamped). */
  .node-popup::after {
    content: "";
    position: absolute;
    left: calc(50% + var(--tail-dx, 0px));
    transform: translateX(-50%);
    border: 6px solid transparent;
  }
  .node-popup:not(.below)::after {
    top: 100%;
    border-top-color: rgba(15, 23, 42, 0.94);
  }
  .node-popup.below::after {
    bottom: 100%;
    border-bottom-color: rgba(15, 23, 42, 0.94);
  }

  .node-popup-name {
    font-family: var(--heading-font, "Space Grotesk", sans-serif);
    font-size: 0.82rem;
    font-weight: 700;
    color: #f1f5f9;
  }

  .node-popup-link {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.78rem;
    font-weight: 600;
    color: #7dd3fc;
    text-decoration: none;
  }
  .node-popup-link:hover {
    color: #bae6fd;
  }

  @keyframes mnet-pop {
    from {
      opacity: 0;
    }
  }

  /* --- Narration cards ---------------------------------------------------- */
  .mnet-steps {
    position: relative;
    z-index: 2;
    list-style: none;
    margin: 0;
    padding: 12vh 0 16vh;
    /* Let the pointer reach the graph between cards; cards opt back in. */
    pointer-events: none;
  }

  .step {
    display: flex;
    justify-content: center;
    margin: 0 0 55vh;
  }

  .step:last-child {
    margin-bottom: 0;
  }

  /* Blurred, slightly transparent card scrolling over the graph. */
  .step-card {
    pointer-events: auto;
    width: min(30rem, 100%);
    background: rgba(15, 23, 42, 0.55);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 16px;
    padding: 1.1rem 1.3rem 1.2rem;
    box-shadow: 0 14px 34px rgba(2, 6, 23, 0.45);
    transition: border-color 0.25s ease;
  }

  .step-card.current {
    border-color: rgba(56, 189, 248, 0.55);
  }

  .step-kicker {
    margin: 0 0 0.3rem;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #7dd3fc;
  }

  .step-title {
    margin: 0;
    font-family: var(--heading-font, "Space Grotesk", sans-serif);
    font-size: 1.1rem;
    font-weight: 700;
    color: #e2e8f0;
    line-height: 1.35;
  }

  .step-body {
    margin: 0.5rem 0 0;
    font-size: 0.9rem;
    line-height: 1.6;
    color: #cbd5e1;
  }

  /* Person names emphasized inside the narration, mirroring the story slides'
     .person-mention. Main people glow in their own story color; bridging
     (secondary) people get a neutral emphasis. */
  .person-mention {
    font-weight: 700;
    color: #f1f5f9;
    text-shadow: 0 0 6px var(--mention-color, rgba(56, 189, 248, 0.35));
  }

  .person-mention-secondary {
    color: #e2e8f0;
    text-shadow: none;
  }

  .tie-list {
    list-style: none;
    margin: 0.8rem 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  .tie {
    border-left: 2px solid rgba(56, 189, 248, 0.6);
    padding-left: 0.6rem;
  }

  .tie.is-secondary {
    border-left-color: rgba(148, 163, 184, 0.55);
  }

  .tie-head {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0.4rem;
  }

  .tie-names {
    font-weight: 600;
    color: #f1f5f9;
    font-size: 0.88rem;
  }

  .tie-rel {
    font-size: 0.72rem;
    color: #7dd3fc;
    letter-spacing: 0.01em;
  }

  .tie.is-secondary .tie-rel {
    color: #cbd5e1;
  }

  .tie-desc {
    margin: 0.15rem 0 0;
    font-size: 0.82rem;
    line-height: 1.5;
    color: #cbd5e1;
  }

  .tie-more {
    margin: 0.5rem 0 0;
    font-size: 0.78rem;
    color: #94a3b8;
  }

  @media (max-width: 640px) {
    .main-label {
      font-size: 11px;
    }
    .secondary-label {
      font-size: 9.5px;
    }
    .step-card {
      width: min(28rem, 100%);
      padding: 0.95rem 1.05rem 1.05rem;
    }
  }
</style>
