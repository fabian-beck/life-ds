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
  import personStylesData from "../../data/person_styles.json";

  // The `social_network` block from a meta story: { nodes: [...], links: [...] }
  export let network = null;
  export let currentLanguage = "en";
  export let metaStoryId = null;

  const personStyles = personStylesData.styles;

  // Jump to a main person's own story, preserving meta-story context (mirrors
  // the navigation used by the meta timeline).
  function goToStory(personId) {
    const fromMeta = metaStoryId ? `?from_meta=${metaStoryId}` : "";
    window.location.hash = `/${currentLanguage}/story/${encodeURIComponent(
      personId
    )}${fromMeta}`;
  }

  const SECONDARY_COLOR = "#94a3b8";
  const LINK_IDLE = "#64748b"; // links when nothing is focused
  const LINK_ACTIVE = "#38bdf8"; // a focused node's own ties (meta accent)
  const LINK_MUTED = "#475569"; // other ties while a node is focused

  // Person primary color from the shared style registry (matches the timeline).
  function primaryColor(personId) {
    return personStyles[personId]?.primary || "#38bdf8";
  }

  // Links carry no colour meaning on their own: they read as neutral until a
  // node is focused, then that node's ties light up in the accent colour while
  // the rest recede. Relationship meaning is conveyed by the explanation panel.
  function linkFocused(link, aId) {
    if (aId == null) return null;
    return link.source === aId || link.target === aId;
  }
  function linkStroke(link, aId) {
    const f = linkFocused(link, aId);
    if (f === null) return LINK_IDLE;
    return f ? LINK_ACTIVE : LINK_MUTED;
  }
  function linkOpacity(link, aId) {
    const f = linkFocused(link, aId);
    const sec = link.kind === "secondary";
    if (f === null) return sec ? 0.5 : 0.75;
    if (f) return sec ? 0.75 : 0.95;
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

  // Humanize a relationship_type for tooltips: "professional/mentor" → "Professional · Mentor".
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
  let hoveredId = null; // transient (pointer over a node)
  let selectedId = null; // pinned by tap/click (persists, mobile-friendly)

  // The node whose ties are highlighted and explained: hover wins, else pin.
  $: activeId = hoveredId ?? selectedId;

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

  // Connections of the active node, described from that person's perspective.
  $: activeNode = activeId ? posById.get(activeId) : null;
  $: activeConnections = activeId ? buildConnections(activeId) : [];

  function buildConnections(id) {
    const strengthRank = { strong: 3, moderate: 2, weak: 1 };
    const out = [];
    for (const l of simLinks) {
      if (l.source !== id && l.target !== id) continue;
      const otherId = l.source === id ? l.target : l.source;
      const other = posById.get(otherId);
      if (!other) continue;
      const selfView = l.endpoints?.[id];
      const view = selfView || l.endpoints?.[otherId] || l;
      out.push({
        otherId,
        otherName: displayName(other.name),
        otherType: other.type,
        relationship: humanizeRelationship(view.relationship_type),
        description: view.relationship_description || "",
        // Whether the description is in the active person's own words, or
        // recalled from the other person's side of the relationship.
        recalledBy: selfView ? null : displayName(other.name),
        rank: strengthRank[l.strength] || 0,
      });
    }
    // Main ties first, then stronger ties, then alphabetical.
    out.sort(
      (a, b) =>
        (a.otherType === "main" ? 0 : 1) - (b.otherType === "main" ? 0 : 1) ||
        b.rank - a.rank ||
        a.otherName.localeCompare(b.otherName)
    );
    return out;
  }

  $: hasNetwork =
    network &&
    Array.isArray(network.nodes) &&
    network.nodes.length > 0 &&
    Array.isArray(network.links) &&
    network.links.length > 0;

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

    // The layout is computed in the BACKGROUND: the simulation runs on d3's
    // async timer (so the main thread is never blocked), but intermediate ticks
    // are NOT rendered — the graph stays hidden behind a placeholder until it
    // has settled, then it appears in its final positions. This way the user
    // never sees nodes drifting (e.g. while scrolling the section into view).
    ready = false;
    simulation = forceSimulation(simNodes)
      .alphaDecay(0.05) // settle in ~130 ticks so it's ready quickly
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
      // Weak temporal pull: drags each node toward its birth-year x (left→right).
      // d3 ignores this for manually placed (pinned) nodes whose fx is set.
      .force("x", forceX((d) => d.tx).strength(0.14))
      .force("y", forceY(height / 2).strength(0.06))
      .force(
        "collide",
        forceCollide().radius((d) =>
          d.type === "main" ? MAIN_R + 22 : SECONDARY_R + 14
        )
      );

    // While ready, render every tick (so dragging animates); before ready,
    // just keep clamping in the background without rendering.
    simulation.on("tick", () => {
      clampNodes();
      if (ready) simNodes = simNodes;
    });
    // Reveal once the layout has settled (also fires after a drag cools down).
    simulation.on("end", () => {
      clampNodes();
      ready = true;
      simNodes = simNodes;
    });

    builtWidth = width;
    simBuilt = true;
  }

  // Keep nodes (and their labels) within the frame. The horizontal inset
  // reserves room for the label text centered under each node; the top strip is
  // reserved for the legend.
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
  // Nodes are not draggable; tapping one toggles its selection (details panel).
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
    if (simulation) simulation.stop();
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
    // Re-settle in the background (hidden), then reveal — same as first build.
    ready = false;
    simulation.alpha(0.8).alphaTarget(0).restart();
    builtWidth = width;
  }
</script>

<svelte:window on:resize={handleResize} />

{#if hasNetwork}
  <div class="mnet">
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
                stroke={linkStroke(link, activeId)}
                stroke-width={linkWidth(link)}
                stroke-dasharray={link.kind === "secondary" ? "5 4" : null}
                opacity={linkOpacity(link, activeId)}
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
            {@const dim = activeId != null && !neighborIds.has(node.id)}
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

      <!-- Legend -->
      <div class="legend" class:hidden={!ready}>
        <span class="legend-item">
          <span class="legend-dot main-dot"></span>
          {$_("meta_story.network_main")}
        </span>
        <span class="legend-item">
          <span class="legend-dot secondary-dot"></span>
          {$_("meta_story.network_secondary")}
        </span>
      </div>
    </div>

    <!-- Explanation panel: a node's ties, described from that person's view -->
    <div
      class="network-explain"
      class:has-active={!!activeNode}
      aria-live="polite"
    >
      {#if activeNode}
        <div class="explain-head">
          <div class="explain-head-text">
            <span class="explain-name">{displayName(activeNode.name)}</span>
            {#if activeNode.roles && activeNode.roles.length}
              <span class="explain-roles">{activeNode.roles.join(", ")}</span>
            {/if}
          </div>
          {#if activeNode.type === "main"}
            <button
              type="button"
              class="explain-jump"
              on:click={() => goToStory(activeNode.id)}
            >
              {$_("meta_story.network_view_story")}
            </button>
          {/if}
        </div>
        {#if activeConnections.length}
          <ul class="explain-list">
            {#each activeConnections as c (c.otherId)}
              <li
                class="explain-item"
                class:is-secondary={c.otherType === "secondary"}
              >
                <div class="explain-item-head">
                  {#if c.otherType === "main"}
                    <button
                      type="button"
                      class="explain-other-link"
                      on:click={() => goToStory(c.otherId)}
                    >
                      {c.otherName}
                    </button>
                  {:else}
                    <span class="explain-other">{c.otherName}</span>
                  {/if}
                  {#if c.relationship}
                    <span class="explain-rel">{c.relationship}</span>
                  {/if}
                </div>
                {#if c.description}
                  <p class="explain-desc">
                    {c.description}
                    {#if c.recalledBy}
                      <span class="explain-recalled"
                        >{$_("meta_story.network_recalled_by", {
                          name: c.recalledBy,
                        })}</span
                      >
                    {/if}
                  </p>
                {/if}
              </li>
            {/each}
          </ul>
        {:else}
          <p class="explain-empty">{$_("meta_story.network_no_connections")}</p>
        {/if}
      {:else}
        <p class="explain-hint">{$_("meta_story.network_hint")}</p>
      {/if}
    </div>
  </div>
{/if}

<style>
  /* Positioned wrapper so the details panel can overlay the graph on mobile. */
  .mnet {
    position: relative;
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

  .legend.hidden {
    display: none;
  }

  @media (prefers-reduced-motion: reduce) {
    .network-svg {
      transition: none;
    }
    .network-loading {
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

  .legend {
    position: absolute;
    top: 10px;
    left: 12px;
    display: flex;
    gap: 1rem;
    font-size: 0.75rem;
    color: #94a3b8;
    background: rgba(15, 23, 42, 0.55);
    backdrop-filter: blur(4px);
    padding: 0.3rem 0.6rem;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.14);
    pointer-events: none;
  }

  .legend-item {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
  }

  .legend-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    display: inline-block;
  }

  .main-dot {
    background: #38bdf8;
    box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.3);
  }

  .secondary-dot {
    background: rgba(148, 163, 184, 0.25);
    border: 1.5px solid #94a3b8;
  }

  /* Explanation panel */
  .network-explain {
    margin-top: 0.85rem;
    padding: 0.85rem 1rem;
    min-height: 4.5rem;
    border-radius: 12px;
    background: rgba(15, 23, 42, 0.4);
    border: 1px solid rgba(148, 163, 184, 0.16);
  }

  .explain-hint {
    margin: 0;
    color: #94a3b8;
    font-size: 0.9rem;
    line-height: 1.5;
  }

  .explain-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.5rem 0.75rem;
    flex-wrap: wrap;
    margin-bottom: 0.6rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.14);
  }

  .explain-head-text {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0.5rem;
    min-width: 0;
  }

  .explain-name {
    font-family: var(--heading-font, "Space Grotesk", sans-serif);
    font-size: 1.05rem;
    font-weight: 700;
    color: #e2e8f0;
  }

  /* "Open story" action for a focused main person. */
  .explain-jump {
    flex: 0 0 auto;
    border: 1px solid rgba(56, 189, 248, 0.5);
    background: rgba(56, 189, 248, 0.12);
    color: #7dd3fc;
    font: inherit;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 0.25rem 0.7rem;
    border-radius: 999px;
    cursor: pointer;
    white-space: nowrap;
    transition:
      background-color 0.15s ease,
      border-color 0.15s ease;
  }
  .explain-jump:hover,
  .explain-jump:focus-visible {
    background: rgba(56, 189, 248, 0.22);
    border-color: rgba(56, 189, 248, 0.8);
    outline: none;
  }

  /* A connection that is itself a main person links to their story. */
  .explain-other-link {
    border: none;
    background: none;
    padding: 0;
    font-family: inherit;
    font-size: 0.92rem;
    font-weight: 600;
    color: #f1f5f9;
    cursor: pointer;
    text-decoration: underline;
    text-decoration-color: rgba(125, 211, 252, 0.45);
    text-underline-offset: 2px;
  }
  .explain-other-link:hover,
  .explain-other-link:focus-visible {
    text-decoration-color: #7dd3fc;
    outline: none;
  }

  .explain-roles {
    font-size: 0.8rem;
    color: #94a3b8;
    text-transform: capitalize;
  }

  .explain-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    max-height: 15rem;
    overflow-y: auto;
  }

  .explain-item {
    border-left: 2px solid rgba(56, 189, 248, 0.6);
    padding-left: 0.6rem;
  }

  .explain-item.is-secondary {
    border-left-color: rgba(148, 163, 184, 0.55);
  }

  .explain-item-head {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0.4rem;
  }

  .explain-other {
    font-weight: 600;
    color: #f1f5f9;
    font-size: 0.92rem;
  }

  .explain-rel {
    font-size: 0.75rem;
    color: #7dd3fc;
    letter-spacing: 0.01em;
  }

  .explain-item.is-secondary .explain-rel {
    color: #cbd5e1;
  }

  .explain-desc {
    margin: 0.15rem 0 0;
    font-size: 0.85rem;
    line-height: 1.5;
    color: #cbd5e1;
  }

  .explain-recalled {
    color: #94a3b8;
    font-style: italic;
  }

  .explain-empty {
    margin: 0;
    color: #94a3b8;
    font-size: 0.88rem;
  }

  @media (max-width: 640px) {
    .main-label {
      font-size: 11px;
    }
    .secondary-label {
      font-size: 9.5px;
    }
    .legend {
      font-size: 0.68rem;
      gap: 0.6rem;
    }

    /* On mobile the details slide up as a bottom sheet over the lower part of
       the graph, so the network and the selection details share one screen. */
    .network-explain {
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      margin: 0;
      max-height: 60%;
      overflow-y: auto;
      -webkit-overflow-scrolling: touch;
      border-radius: 14px 14px 0 0;
      background: rgba(15, 23, 42, 0.94);
      backdrop-filter: blur(8px);
      border: 1px solid rgba(148, 163, 184, 0.2);
      box-shadow: 0 -10px 24px rgba(2, 6, 23, 0.5);
    }
    /* Keep the whole graph visible until something is selected. */
    .network-explain:not(.has-active) {
      display: none;
    }
    .explain-list {
      max-height: none;
    }
  }
</style>
