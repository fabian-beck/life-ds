<script>
  import { onMount, onDestroy } from "svelte";
  import {
    forceSimulation,
    forceManyBody,
    forceLink,
    forceCenter,
    forceCollide,
    forceX,
    forceY,
  } from "d3-force";
  import { _ } from "../stores/language.js";
  import { displayName } from "../utils/helpers.js";
  import personStylesData from "../../data/person_styles.json";

  // The `social_network` block from a meta story: { nodes: [...], links: [...] }
  export let network = null;

  const personStyles = personStylesData.styles;

  // Relationship-category palette (matches the accent-driven meta story look).
  const CATEGORY_COLORS = {
    family: "#f472b6",
    professional: "#38bdf8",
    friendship: "#34d399",
    intellectual: "#a78bfa",
    romantic: "#fb7185",
    adversarial: "#f87171",
    social: "#38bdf8",
    academic: "#a78bfa",
    other: "#94a3b8",
  };
  const SECONDARY_COLOR = "#94a3b8";

  function categoryOf(relationshipType) {
    if (!relationshipType) return "other";
    const cat = relationshipType.split("/")[0].toLowerCase();
    return CATEGORY_COLORS[cat] ? cat : "other";
  }

  function categoryColor(relationshipType) {
    return CATEGORY_COLORS[categoryOf(relationshipType)];
  }

  // Person primary color from the shared style registry (matches the timeline).
  function primaryColor(personId) {
    return personStyles[personId]?.primary || "#38bdf8";
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
  let hoveredId = null;

  // Rendered node positions resolved by id (kept in sync with the simulation on
  // every tick). Links read positions from here rather than from d3's mutated
  // link.source/target objects, so endpoints always match the drawn nodes.
  $: posById = new Map(simNodes.map((n) => [n.id, n]));

  // IDs of nodes adjacent to the hovered node (for highlight/dimming).
  let neighborIds = new Set();

  $: hasNetwork =
    network &&
    Array.isArray(network.nodes) &&
    network.nodes.length > 0 &&
    Array.isArray(network.links) &&
    network.links.length > 0;

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

    if (simulation) simulation.stop();

    simulation = forceSimulation(simNodes)
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
      .force("center", forceCenter(width / 2, height / 2))
      .force("x", forceX(width / 2).strength(0.05))
      .force("y", forceY(height / 2).strength(0.07))
      .force(
        "collide",
        forceCollide().radius((d) =>
          d.type === "main" ? MAIN_R + 22 : SECONDARY_R + 14
        )
      )
      .on("tick", () => {
        // Keep nodes (and their labels) within the frame. The horizontal inset
        // reserves room for the label text centered under each node.
        for (const n of simNodes) {
          const r = n.type === "main" ? MAIN_R : SECONDARY_R;
          const ix = n.type === "main" ? insetX : insetX - 22;
          n.x = Math.max(ix, Math.min(width - ix, n.x));
          // Reserve a top strip for the legend. Labels render below nodes, so a
          // top-anchored legend can't collide with them; the bottom only needs
          // to clear each node's own label.
          n.y = Math.max(r + 40, Math.min(height - r - 24, n.y));
        }
        simNodes = simNodes; // trigger Svelte reactivity
      });
    simBuilt = true;
  }

  // Rebuild once the width is known; rebuild again when the story changes.
  $: (network, (simBuilt = false));
  $: if (hasNetwork && width && !simBuilt) {
    buildSimulation();
  }

  function reheat() {
    if (simulation) simulation.alphaTarget(0.3).restart();
  }
  function cool() {
    if (simulation) simulation.alphaTarget(0);
  }

  // --- Dragging (native pointer events) ------------------------------------
  let dragId = null;

  function svgPoint(evt) {
    const rect = container.getBoundingClientRect();
    return { x: evt.clientX - rect.left, y: evt.clientY - rect.top };
  }

  function onPointerDown(evt, node) {
    dragId = node.id;
    node.fx = node.x;
    node.fy = node.y;
    reheat();
    evt.target.setPointerCapture?.(evt.pointerId);
    evt.stopPropagation();
  }
  function onPointerMove(evt) {
    if (dragId == null) return;
    const node = simNodes.find((n) => n.id === dragId);
    if (!node) return;
    const p = svgPoint(evt);
    node.fx = p.x;
    node.fy = p.y;
  }
  function onPointerUp() {
    if (dragId == null) return;
    const node = simNodes.find((n) => n.id === dragId);
    if (node) {
      node.fx = null;
      node.fy = null;
    }
    dragId = null;
    cool();
  }

  // --- Hover highlight ------------------------------------------------------
  function setHovered(id) {
    hoveredId = id;
    const next = new Set();
    if (id != null) {
      next.add(id);
      for (const l of simLinks) {
        if (l.source === id) next.add(l.target);
        if (l.target === id) next.add(l.source);
      }
    }
    neighborIds = next;
  }

  function isLinkActive(l) {
    if (hoveredId == null) return true;
    return l.source === hoveredId || l.target === hoveredId;
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

  function handleResize() {
    if (!container) return;
    width = container.clientWidth;
    // Recenter the existing layout instead of rebuilding (keeps positions).
    if (simulation && width) {
      simulation.force("center", forceCenter(width / 2, height / 2));
      simulation.force("x", forceX(width / 2).strength(0.05));
      simulation.alphaTarget(0.1).restart();
      setTimeout(cool, 400);
    }
  }
</script>

<svelte:window
  on:resize={handleResize}
  on:pointermove={onPointerMove}
  on:pointerup={onPointerUp}
/>

{#if hasNetwork}
  <div
    class="network-frame"
    bind:this={container}
    bind:clientWidth={width}
    style="height: {height}px;"
  >
    <svg
      class="network-svg"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={$_("meta_story.network_aria")}
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
              stroke={categoryColor(link.relationship_type)}
              stroke-width={link.kind === "secondary" ? 1.5 : 3}
              stroke-dasharray={link.kind === "secondary" ? "5 4" : null}
              opacity={isLinkActive(link)
                ? link.kind === "secondary"
                  ? 0.6
                  : 0.9
                : 0.1}
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
          {@const dim = hoveredId != null && !neighborIds.has(node.id)}
          <g
            class="node"
            class:main={node.type === "main"}
            class:secondary={node.type === "secondary"}
            transform={`translate(${node.x ?? width / 2}, ${node.y ?? height / 2})`}
            opacity={dim ? 0.25 : 1}
            on:pointerdown={(e) => onPointerDown(e, node)}
            on:pointerenter={() => setHovered(node.id)}
            on:pointerleave={() => setHovered(null)}
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
                stroke-width="3"
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
                fill={SECONDARY_COLOR}
                fill-opacity="0.22"
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
    <div class="legend">
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
{/if}

<style>
  .network-frame {
    position: relative;
    width: 100%;
    border-radius: 16px;
    background:
      radial-gradient(
        circle at 50% 35%,
        rgba(56, 189, 248, 0.06),
        transparent 60%
      ),
      rgba(15, 23, 42, 0.35);
    border: 1px solid rgba(148, 163, 184, 0.16);
    overflow: hidden;
    touch-action: none;
  }

  .network-svg {
    display: block;
    width: 100%;
    height: 100%;
  }

  .node {
    cursor: grab;
  }
  .node:active {
    cursor: grabbing;
  }

  .halo {
    filter: drop-shadow(0 0 6px rgba(56, 189, 248, 0.35));
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
  }
</style>
