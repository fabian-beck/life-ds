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
  import { assetUrl } from "../utils/assetUrl.js";
  import { displayName } from "../utils/helpers.js";
  import { computeClusters } from "../utils/networkClusters.js";
  import { segmentPersonMentions } from "../utils/personNames.js";
  import { metaStoryStyle } from "../utils/metaStoryStyles.js";
  import { saveMetaStoryScroll } from "../stores/metaStoryScroll.js";
  import { relationshipTypeLabel } from "../utils/relationshipLabels.js";
  import { queryParams, originQuery } from "../stores/queryParams.js";
  import personStylesData from "../../data/person_styles.json";

  // The `social_network` block from a meta story: { nodes: [...], links: [...] }
  export let network = null;
  export let currentLanguage = "en";
  // Id of the meta story this network belongs to, so opening a person's story
  // carries the `from_meta` context (returning restores the meta story + scroll).
  export let metaStoryId = null;
  // Extra names per person id (e.g. the translated registry name), so a
  // translated story still recognizes its people in the narration prose.
  export let personAliases = null;

  const personStyles = personStylesData.styles;

  const SECONDARY_COLOR = "#94a3b8";
  const LINK_IDLE = "#64748b"; // links when nothing is focused
  const LINK_MUTED = "#475569"; // other ties while something is focused

  // Focused ties take the story's own accent. Read here rather than through a
  // CSS variable because the stroke is an SVG presentation attribute, and
  // those do not resolve var().
  $: linkActive = metaStoryStyle(metaStoryId)?.primary ?? "#38bdf8";

  // Whether the story has a glyph to open its narration cards with.
  $: storyMarked = !!metaStoryStyle(metaStoryId)?.separatorGlyphDataUrl;

  function hashString(value) {
    let hash = 2166136261;
    for (let i = 0; i < value.length; i++) {
      hash ^= value.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }

  // A graph-derived pseudo-random source keeps force initialization identical
  // whenever the reader returns to the same meta story.
  function seededRandom(seed) {
    let state = hashString(seed) || 1;
    return () => {
      state = (Math.imul(1664525, state) + 1013904223) >>> 0;
      return state / 4294967296;
    };
  }

  // How many ties a cluster card spells out before summarizing the rest.
  const MAX_CARD_TIES = 4;

  // Person primary color from the shared style registry (matches the timeline).
  function primaryColor(personId) {
    return personStyles[personId]?.primary || "#38bdf8";
  }

  // Links carry no color meaning on their own: they read as neutral until a
  // node is hovered/tapped or a cluster card is in view, then the focused ties
  // light up in the accent color while the rest recede.
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
  function linkStroke(link, aId, cIds, active) {
    const s = linkState(link, aId, cIds);
    return s === "idle" ? LINK_IDLE : s === "active" ? active : LINK_MUTED;
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

  // Every link is masked by the node discs (see the `mnet-node-mask` in the
  // template), so a line stops at a node's outer edge instead of running under
  // it. Radius of the hole a node punches: the outer edge of the halo ring for
  // main nodes, of the stroked circle for secondary ones.
  function maskRadius(node, mainR, secondaryR) {
    return node.type === "main" ? mainR + 5 : secondaryR + 2;
  }

  // Name a relationship_type: "professional/mentor" → "Professional · Mentor".
  // The token is machine-readable and identical in every language's dataset,
  // so both of its segments are resolved through the locale.
  function humanizeRelationship(relationshipType) {
    return relationshipTypeLabel($_, relationshipType);
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

  // Label sizing. The font size is set inline (not from CSS) because the wrap
  // width below is computed from it — a media query that disagreed with the
  // JS breakpoint would break lines in the wrong places.
  $: MAIN_LABEL_FS = compact ? 11 : 13;
  $: SECONDARY_LABEL_FS = compact ? 9.5 : 10.5;
  $: MAIN_LABEL_MAX_W = compact ? 104 : 150;
  $: SECONDARY_LABEL_MAX_W = compact ? 84 : 110;
  $: MAIN_LINE_H = MAIN_LABEL_FS + 2;
  $: SECONDARY_LINE_H = SECONDARY_LABEL_FS + 2;

  // Horizontal insets reserve room for the (centered, wrapped) label under a
  // node, so no name can be clipped at the frame edge.
  $: insetX = MAIN_LABEL_MAX_W / 2 + 6;
  $: secondaryInsetX = SECONDARY_LABEL_MAX_W / 2 + 6;

  // SVG text does not wrap, so long names are split into lines by an estimated
  // advance width — the label font may not even be loaded when the layout is
  // computed, which makes measuring unreliable at that moment.
  const NARROW_CHARS = new Set([..."ijlrtfI.,;:'!|( )"]);
  const WIDE_CHARS = new Set([..."MWmw@"]);
  function estimateTextWidth(text, fontSize) {
    let units = 0;
    for (const ch of text) {
      units += NARROW_CHARS.has(ch) ? 0.36 : WIDE_CHARS.has(ch) ? 0.92 : 0.6;
    }
    return units * fontSize;
  }

  // Greedy word wrap. Once the last allowed line is reached the remaining words
  // stay on it — an overlong final line beats dropping part of a name.
  function wrapLabel(text, fontSize, maxWidth, maxLines) {
    const words = String(text ?? "")
      .split(/\s+/)
      .filter(Boolean);
    if (!words.length) return [];
    const lines = [];
    let current = words[0];
    for (const word of words.slice(1)) {
      const candidate = `${current} ${word}`;
      const onLastLine = lines.length === maxLines - 1;
      if (!onLastLine && estimateTextWidth(candidate, fontSize) > maxWidth) {
        lines.push(current);
        current = word;
      } else {
        current = candidate;
      }
    }
    lines.push(current);
    return lines;
  }

  const MAX_LABEL_LINES = 3;

  function labelLines(node) {
    const main = node.type === "main";
    return wrapLabel(
      displayName(node.name),
      main ? MAIN_LABEL_FS : SECONDARY_LABEL_FS,
      main ? MAIN_LABEL_MAX_W : SECONDARY_LABEL_MAX_W,
      MAX_LABEL_LINES
    );
  }

  // Vertical room a node's label needs below its center (offset + wrapped
  // lines + a little breathing space at the frame edge).
  function labelExtent(node) {
    const main = node.type === "main";
    const lines = labelLines(node).length || 1;
    const lineHeight = main ? MAIN_LINE_H : SECONDARY_LINE_H;
    return (main ? 16 : 13) + (lines - 1) * lineHeight + 8;
  }

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
  // Carry the meta story context so the story's close button returns here,
  // together with any landing filters behind it.
  $: popupOrigin = originQuery(metaStoryId, $queryParams.from_landing);
  $: popupHref = popupNode
    ? `#/${currentLanguage}/story/${popupNode.id}` +
      (popupOrigin ? `?${popupOrigin}` : "")
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
  // the way person names are emphasized in the story slides. The nodes carry
  // the untranslated name, so `personAliases` supplies the name the reader
  // actually sees in a translated story.
  function highlightNarration(text, cluster) {
    const people = [...cluster.mains, ...cluster.secondaries].map((person) => ({
      ...person,
      aliases: personAliases?.[person.id] ?? [],
    }));
    return segmentPersonMentions(text, people);
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

  // SVG has no z-index — paint order IS document order. So links and nodes are
  // drawn from ONE re-sorted list instead of two fixed groups, in four layers:
  // dimmed links, dimmed nodes, highlighted links, highlighted nodes. A
  // highlighted tie therefore runs in front of the dimmed portraits and labels
  // it passes, while the highlighted nodes still cap their own edges. With
  // nothing highlighted this collapses to the plain "all links, then all
  // nodes" order.
  function buildDrawItems(links, nodes, aId, nIds, cIds) {
    const items = [];
    for (const link of links) {
      items.push({
        kind: "link",
        key: `l:${link.source}-${link.target}`,
        link,
        layer: linkState(link, aId, cIds) === "active" ? 2 : 0,
      });
    }
    for (const node of nodes) {
      const dim = isDimmed(node.id, aId, nIds, cIds);
      items.push({
        kind: "node",
        key: `n:${node.id}`,
        node,
        dim,
        layer: dim ? 1 : 3,
      });
    }
    // Array.sort is stable, so ordering within a layer stays as built.
    return items.sort((a, b) => a.layer - b.layer);
  }

  $: drawItems = buildDrawItems(
    simLinks,
    simNodes,
    activeId,
    neighborIds,
    clusterIds
  );

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
    const layoutSeed = [
      ...simNodes.map((n) => `n:${n.id}`).sort(),
      ...valid.map((l) => `l:${[l.source, l.target].sort().join("-")}`).sort(),
    ].join("|");
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
      const nodeRandom = seededRandom(`${layoutSeed}|${n.id}`);
      n.y = height / 2 + (nodeRandom() - 0.5) * height * 0.5;
    }

    if (simulation) simulation.stop();

    // Create the simulation STOPPED — the layout is computed off the render path
    // (see runLayout) so the graph never animates on its own.
    simulation = forceSimulation(simNodes)
      .stop()
      .randomSource(seededRandom(layoutSeed))
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
  // reserves room for the wrapped label centered under each node; the top strip
  // keeps nodes and their upper halo clear of the frame edge, and the bottom
  // one grows with the number of label lines.
  function clampNodes() {
    for (const n of simNodes) {
      const r = n.type === "main" ? MAIN_R : SECONDARY_R;
      const ix = n.type === "main" ? insetX : secondaryInsetX;
      n.x = Math.max(ix, Math.min(width - ix, n.x));
      n.y = Math.max(r + 40, Math.min(height - r - labelExtent(n), n.y));
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

            <!-- Holes at every node, applied to every link: a line stops at the
                 node's outer edge rather than being drawn under it, so a
                 portrait always reads as being in front of the links — both
                 the ties ending at it and the ones merely passing over it,
                 which the draw order otherwise puts on top of dimmed nodes. -->
            <mask
              id="mnet-node-mask"
              maskUnits="userSpaceOnUse"
              x="0"
              y="0"
              {width}
              {height}
            >
              <rect x="0" y="0" {width} {height} fill="white" />
              {#each simNodes as node (node.id)}
                <circle
                  cx={node.x ?? width / 2}
                  cy={node.y ?? height / 2}
                  r={maskRadius(node, MAIN_R, SECONDARY_R)}
                  fill="black"
                />
              {/each}
            </mask>
          </defs>

          <!-- Links and nodes share one list so highlighted ties can be lifted
               above dimmed nodes (see buildDrawItems). -->
          <g class="draw" stroke-linecap="round">
            {#each drawItems as item (item.key)}
              {#if item.kind === "link"}
                {@const link = item.link}
                {@const s = posById.get(link.source)}
                {@const t = posById.get(link.target)}
                {#if s && t}
                  <line
                    mask="url(#mnet-node-mask)"
                    x1={s.x}
                    y1={s.y}
                    x2={t.x}
                    y2={t.y}
                    stroke={linkStroke(link, activeId, clusterIds, linkActive)}
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
              {:else}
                {@const node = item.node}
                {@const dim = item.dim}
                <g
                  class="node"
                  class:main={node.type === "main"}
                  class:secondary={node.type === "secondary"}
                  class:dim
                  class:selected={node.id === selectedId}
                  transform={`translate(${node.x ?? width / 2}, ${node.y ?? height / 2})`}
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
                        href={assetUrl(node.portrait)}
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
                    <text
                      class="label main-label"
                      y={MAIN_R + 16}
                      style="font-size: {MAIN_LABEL_FS}px"
                      >{#each labelLines(node) as line, i}<tspan
                          x="0"
                          dy={i === 0 ? 0 : MAIN_LINE_H}>{line}</tspan
                        >{/each}</text
                    >
                  {:else}
                    <circle
                      r={SECONDARY_R}
                      fill="#1e293b"
                      stroke={SECONDARY_COLOR}
                      stroke-width="1.5"
                    />
                    <text
                      class="label secondary-label"
                      y={SECONDARY_R + 13}
                      style="font-size: {SECONDARY_LABEL_FS}px"
                      >{#each labelLines(node) as line, i}<tspan
                          x="0"
                          dy={i === 0 ? 0 : SECONDARY_LINE_H}>{line}</tspan
                        >{/each}</text
                    >
                  {/if}
                </g>
              {/if}
            {/each}
          </g>

          <!-- Hit targets and tooltips, in a layer that is NEVER reordered:
               the draw layer above moves its elements around on every
               highlight change, and moving the element under the pointer
               makes browsers fire a spurious pointerleave — which would
               cancel the very hover that caused the move. -->
          <g class="hits">
            {#each simNodes as node (node.id)}
              <g
                class="hit"
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
                <circle
                  r={node.type === "main" ? MAIN_R + 3 : SECONDARY_R + 2}
                  fill="transparent"
                />
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
            <div
              class="step-card ms-frame"
              class:current={activeStep === i}
              class:marked={storyMarked}
            >
              <h3 class="step-title">
                {narrationTitles.get(cluster.key) ??
                  clusterTitle(cluster, currentLanguage)}
              </h3>
              {#if narrationTexts.has(cluster.key)}
                <p class="step-body">
                  {#each highlightNarration(narrationTexts.get(cluster.key), cluster) as seg}{#if seg.type === "text"}{seg.content}{:else if seg.person.type === "main"}<strong
                        class="person-mention"
                        style={`--mention-color: ${primaryColor(
                          seg.person.id
                        )}`}>{seg.content}</strong
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
    /* Give the narration cards a clean backdrop root that already contains the
       pinned graph, so backdrop-filter samples it. Without this some mobile
       browsers composite the sticky graph on a separate layer that the card's
       backdrop can't reach, and the blur silently no-ops. */
    isolation: isolate;
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
      color-mix(in srgb, var(--ms-accent, #38bdf8) 5%, transparent),
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

  /* Purely visual: the draw layer is re-sorted for stacking, so all pointer
     interaction lives in the stable .hits layer instead. */
  .node {
    pointer-events: none;
    transition: filter 0.18s ease;
  }

  .hit {
    cursor: pointer;
  }

  /* Blend out non-focused nodes by DARKENING them (kept fully opaque) so the
     links that sit behind them do not shine through. */
  .node.dim {
    filter: brightness(0.32) saturate(0.5);
  }

  .halo {
    filter: drop-shadow(
      0 0 6px color-mix(in srgb, var(--ms-accent, #38bdf8) 35%, transparent)
    );
  }

  .node.selected .halo {
    filter: drop-shadow(
      0 0 9px color-mix(in srgb, var(--ms-accent, #38bdf8) 60%, transparent)
    );
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

  /* font-size is set inline — the wrap width is derived from it in JS. */
  .main-label {
    font-weight: 600;
  }

  .secondary-label {
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
    background: rgba(var(--ms-page-bg-rgb, 15, 23, 42), 0.94);
    border: var(--ms-frame-border-width, 1px)
      var(--ms-frame-border-style, solid)
      color-mix(in srgb, var(--ms-accent, #38bdf8) 45%, transparent);
    border-radius: var(--ms-frame-radius, 10px);
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
    border-top-color: rgba(var(--ms-page-bg-rgb, 15, 23, 42), 0.94);
  }
  .node-popup.below::after {
    bottom: 100%;
    border-bottom-color: rgba(var(--ms-page-bg-rgb, 15, 23, 42), 0.94);
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
    color: var(--ms-accent, #7dd3fc);
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

  /* Card scrolling over the graph. Default to a near-opaque panel so the text
     stays readable on browsers/devices where backdrop-filter doesn't render
     (notably some Android browsers) — otherwise the sharp graph shows straight
     through and fights the copy. Where backdrop-filter IS supported, the rule
     below drops the scrim to a translucent frosted glass. */
  .step-card {
    pointer-events: auto;
    width: min(30rem, 100%);
    background: rgba(var(--ms-page-bg-rgb, 15, 23, 42), 0.88);
    border: var(--ms-frame-border-width, 1px)
      var(--ms-frame-border-style, solid)
      color-mix(
        in srgb,
        var(--ms-accent, #38bdf8) 22%,
        rgba(148, 163, 184, 0.22)
      );
    border-radius: var(--ms-frame-radius, 16px);
    padding: 1.1rem 1.3rem 1.2rem;
    box-shadow: 0 14px 34px rgba(2, 6, 23, 0.45);
    transition: border-color 0.25s ease;
  }

  /* Unprefixed only — never hand-write `-webkit-backdrop-filter` next to the
     standard property. The production build minifies with LightningCSS,
     which folds such a pair into one logical declaration where the LAST one
     wins: the built CSS then carried ONLY the -webkit- alias, which Chrome
     ignores, so the deployed cards never blurred — while the dev server
     serves the source unminified, which is why desktop checks against
     `npm run dev` kept looking fine. From the bare standard property the
     minifier itself re-emits the -webkit- fallback (and widens this
     @supports probe) for the browsers that need it. */
  @supports (backdrop-filter: blur(20px)) {
    .step-card {
      background: rgba(var(--ms-page-bg-rgb, 15, 23, 42), 0.45);
      backdrop-filter: blur(20px) saturate(1.3);
    }
  }

  .step-card.current {
    border-color: color-mix(
      in srgb,
      var(--ms-accent, #38bdf8) 55%,
      transparent
    );
  }

  /* Every heading in a styled story opens with the story's mark — the article's
     subheads do it, and so do the cards that narrate its components, so a card
     scrolling over the graph or the map belongs to the same document as the
     prose above it. Rendered only when the story has a glyph; without one the
     title keeps its plain setting. */
  .step-card.marked .step-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .step-card.marked .step-title::before {
    content: "";
    flex: 0 0 auto;
    width: 0.85em;
    height: 0.85em;
    background-image: var(--ms-glyph, none);
    background-position: center;
    background-size: contain;
    background-repeat: no-repeat;
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
    border-left: 2px solid
      color-mix(in srgb, var(--ms-accent, #38bdf8) 60%, transparent);
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
    color: var(--ms-accent, #7dd3fc);
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
    /* On phones the graph breaks out of the story column and uses the full
       viewport width (same full-bleed trick as the map section), so a crowded
       cast gets every pixel available. The narration cards stay in the column. */
    .mnet-sticky {
      width: 100vw;
      margin-left: calc(-50vw + 50%);
    }

    .step-card {
      width: min(28rem, 100%);
      padding: 0.95rem 1.05rem 1.05rem;
    }
  }
</style>
