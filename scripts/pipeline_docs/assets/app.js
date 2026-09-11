/* Technical report—computed content and interaction.
   The page is a pure function of window.PIPELINE, which the Python build emits.
   Layout runs client-side so the chart can be sized to its column.

   The document body is compiled from Markdown and arrives already written; this
   file only fills the holes left in it. Every `div.widget[data-component]` the
   Markdown placed is hydrated by the matching entry in COMPONENTS, in document
   order, so *where* a figure appears is an authoring decision while *what* it
   contains is a build-time computation. Adding a section to the report never
   touches this file; adding a new kind of computed block means one COMPONENTS
   entry here and one in `report.py`.

   Both pipelines are drawn, as two subsections rather than two tabs, so the
   report reads straight through and either chart can be cited from anywhere in
   the prose. Each chart is an independent instance with its own selection;
   the step note is shared, and opening it from one chart clears the other's
   selection. Color encodes the step kind and nothing else.

   The chart is a layered DAG, not a sequence. A step's layer is the longest
   path of real data dependencies reaching it, so steps drawn side by side are
   genuinely independent—the map branch and the network branch of the meta
   story really do run without seeing each other. Only edges the spec declares
   directly are drawn—one a longer chain already implies is left out there, so
   the chart never carries a line beside a strand that says the same thing.
   The files a step reads and writes are not drawn: the step note and the
   appendix list them, so the chart carries the steps, the flow, and the phases.

   The vertical axis is the dependency graph; the horizontal axis is free, and
   `spec.GROUPS` spends it on meaning: the phases. Steps of one concern—plan
   the image searches, run them, match the results—are aligned and banded, so
   a job that takes three layers reads as one vertical strand instead of
   drifting across the chart. Every step is in a phase.
   Alignment holds only where a group is continuous: a member several
   layers below the rest is placed on its own. Positions are continuous, not
   slots in a grid, and are relaxed to keep the edges short. */

(function () {
  "use strict";

  const DATA = window.PIPELINE;
  const SVG_NS = "http://www.w3.org/2000/svg";

  /* Chart geometry, in SVG user units, at two levels of detail.

     They are the same graph—same layers, same order, same bands—drawn with
     more or less written inside a node, and sized to match:

       mid      the name, the kind and the model. 660 units.
       compact  the name. 398.

     Both scale to the column they are given, and the one whose names come out
     largest is drawn. A reduced drawing is not a larger one shrunk: fitting
     the mid drawing into a 350-unit column would put its 11px type on screen
     at 6px, which is not a reduced figure but an unreadable one. Each is a
     drawing with less in it, laid out at its own size, so what survives stays
     legible; what either leaves out is one selection away, in the step note.

     The chart once had a third, full-size level with the script, the model,
     and the files written inside every node, opened over the whole viewport.
     It was the drawing of an engineer's wall chart rather than a figure in a
     report, and it went. */
  const METRICS = {
    mid: {
      TITLE_PX: 11, // the step-name type; mirrors style.css
      RAIL_W: 40,
      RAIL_GAP: 14, // rule to node: where the layer number is written
      RAIL_DX: 6,
      RAIL_DY: 11,
      NODE_W: 176,
      NODE_H: 44,
      COL_GAP: 20,
      LAYER_GAP: 30,
      MARGIN_CH: 18, // side channels for edges that skip a layer
      PAD: 8,
      BAND_PAD: 7,
      BAND_HEAD: 19, // room for a phase band's label above its first step
      BAND_LABEL_CH: 6, // width per character of the label's box
      BAND_LABEL_H: 15,
      BAND_LABEL_DY: 13, // the label's baseline, down from the band's top
      LABEL_PAD: 10,
      LABEL_LINES: 2,
      LINE_H: 13,
      FACT_UP: 6, // the kind-and-model line, up from the node's foot
    },
    compact: {
      TITLE_PX: 9,
      RAIL_W: 26,
      RAIL_GAP: 8,
      RAIL_DX: 4,
      RAIL_DY: 9,
      NODE_W: 104,
      NODE_H: 34,
      COL_GAP: 12,
      LAYER_GAP: 26,
      MARGIN_CH: 12,
      PAD: 6,
      BAND_PAD: 5,
      BAND_HEAD: 14, // the phase label, set smaller, still names the band
      BAND_LABEL_CH: 4.6,
      BAND_LABEL_H: 11,
      BAND_LABEL_DY: 9.5,
      LABEL_PAD: 9,
      LABEL_LINES: 2,
      LINE_H: 11,
      FACT_UP: 0, // no fact line: the name is all a compact node carries
    },
  };
  Object.keys(METRICS).forEach((size) => {
    // A band on the first layer has to fit above it.
    METRICS[size].HEAD_H = METRICS[size].BAND_HEAD + 4;
  });

  // Largest first: the sizes, in the order they are offered a column.
  const SIZES = ["mid", "compact"];

  // A reduced node wraps the step's name to `LABEL_LINES`; `fitLines` measures
  // the rest. The character count is only the fallback for a chart drawn where
  // nothing can be measured.
  const COMPACT_LINE_CH = 15;

  /* How large a reduced drawing is allowed to be rendered.

     It fits the width it is given, but width alone is not enough of a rule. In
     a mid-size column, fitting is an instruction to enlarge: the compact figure
     scaled to a 676-unit column stands 1107 units tall and sets 15px type,
     which is a poster, not a reduced figure. So the height of the viewport
     bounds it too, and a ceiling stops it outgrowing the prose it sits in.

     The floor works the other way. A short window would otherwise shrink the
     figure to nothing; below this the drawing keeps its size and the page
     scrolls, which is what a document does anyway.

     `TIER_TYPE_TOLERANCE` settles which reduced size to use. They all scale to
     the room, so the question is not which carries the most but which still
     sets its names largest once fitted: a mid drawing squeezed by a short
     window carries more than the compact one and reads worse. A size is taken
     if its rendered type comes within this of the best on offer: a richer
     drawing may read a tenth smaller and still win, because it carries more.
     Tighter than this and the rule turns on rounding—at 0.95 a tall tablet
     chose compact over mid on a difference of two hundredths of a pixel. */
  const COMPACT_HEIGHT_BUDGET = 0.9; // of the viewport
  const COMPACT_MAX_SCALE = 1.6; // 9px type drawn at no more than 14.4px
  const COMPACT_MIN_SCALE = 0.8;
  const TIER_TYPE_TOLERANCE = 0.9;

  /* The widest capture that is offered the margin beside the text rather than a
     block of its own. It divides the two kinds of screenshot this report takes:
     a phone, held upright, which is 390 to 430 CSS pixels across and would leave
     more than half the column empty if it were set as a block; and a desktop
     view, declared at 1280, which is wider than the measure and needs the room.
     Set between them, so neither kind is a special case. */
  const MARGIN_FIGURE_MAX = 500;
  /* A portrait capture is shown smaller than it was taken. At its own CSS
     pixels a phone screen stands on the page as large as the reader's phone,
     more room than a figure beside a paragraph needs; at four fifths it still
     reads, and a part drawn too small to read is enlarged in place anyway. */
  const MARGIN_FIGURE_SCALE = 0.8;

  // Live chart instances, so the shared step note can clear the selection in the
  // chart the reader did *not* click.
  const charts = [];

  /* ------------------------------------------------------------ helpers */

  function el(tag, props, children) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach((entry) => {
      const key = entry[0];
      const value = entry[1];
      if (key === "class") node.className = value;
      else if (key === "html") node.innerHTML = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else if (value !== null && value !== undefined)
        node.setAttribute(key, value);
    });
    (children || []).forEach((child) => {
      if (child) node.appendChild(child);
    });
    return node;
  }

  function svg(tag, props) {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(props || {}).forEach((entry) => {
      if (entry[1] !== null && entry[1] !== undefined) {
        node.setAttribute(entry[0], String(entry[1]));
      }
    });
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function truncateLabel(text, max) {
    return text.length > max ? text.slice(0, max - 1) + "…" : text;
  }

  /* Break a step's name onto at most `lines` lines that fit in `width` units.
     SVG text does not wrap and the compact node is far too narrow for a name on
     one line, so the wrapping is done here—greedily, on words, with the
     overflow ending in an ellipsis.

     It fits by measuring rather than by counting characters. A budget in
     characters has to assume an average glyph, and these names are nothing like
     the average: fifteen characters of "Phase 8—compose" run six units wider
     than fifteen of "Save story and", which is the difference between a label
     with a margin and one touching the border of its box. The browser can
     measure the exact string it is about to draw, so it is asked. */
  function fitLines(root, text, width, lines, className) {
    // The probe has to sit inside a `.node`, and carry the class of the line it
    // stands in for—a title and a fact line are set at different sizes, and a
    // fact line measured as a title would be cut short of its own box. Parked
    // off-canvas, and removed before anything is drawn.
    const scratch = svg("g", { class: "node" });
    const probe = svg("text", { class: className || "title", x: 0, y: -999 });
    scratch.appendChild(probe);
    root.appendChild(scratch);

    function measure(value) {
      probe.textContent = value;
      return probe.getComputedTextLength();
    }
    // A chart drawn while detached or hidden measures every string as zero.
    // Counting characters is the poorer rule, but it is a rule.
    const measurable = measure("Mm") > 0;
    function fits(value) {
      return measurable
        ? measure(value) <= width
        : value.length <= COMPACT_LINE_CH;
    }

    /* An em dash inside a word is a break opportunity, and half the steps are
       named "Phase 5b—review network". Treated as one word it does not fit, so
       the line turns before it and leaves "Phase" alone above an ellipsis; cut
       at the dash, the whole name fits. The dash stays on the line it ends, and
       what follows it is joined without a space. */
    const tokens = [];
    text
      .split(/\s+/)
      .filter(Boolean)
      .forEach((word) => {
        (word.match(/[^—]*—|[^—]+/g) || [word]).forEach((piece, index) => {
          tokens.push({ text: piece, glued: index > 0 });
        });
      });

    const out = [];
    let current = "";
    tokens.forEach((token) => {
      const candidate = current
        ? current + (token.glued ? "" : " ") + token.text
        : token.text;
      if (!current || fits(candidate)) current = candidate;
      else {
        out.push(current);
        current = token.text;
      }
    });
    if (current) out.push(current);

    const kept = out.slice(0, lines);
    kept.forEach((line, index) => {
      // The last line has to say that it is not the end of the name; any line
      // may still be a single word wider than the box.
      const cut = out.length > lines && index === lines - 1;
      if (!cut && fits(line)) return;
      let value = line;
      while (value.length > 1 && !fits(value + "…")) value = value.slice(0, -1);
      kept[index] = value.replace(/[\s—–-]+$/, "") + "…";
    });

    root.removeChild(scratch);
    return kept;
  }

  const stepById = {};
  DATA.steps.forEach((step, index) => {
    step._order = index;
    stepById[step.id] = step;
  });

  const artifactById = {};
  DATA.artifacts.forEach((artifact) => {
    artifactById[artifact.id] = artifact;
  });

  /* The concept vocabulary and its glyphs.

     Every artifact carries a concept, every concept carries the icon the
     application already draws for it, and the two together are why nothing on
     this page needs to name a path: a reader who has seen the network glyph
     above a story recognizes the same mark on the node that writes the graph.
     Icons are Material Design Icons on a 24-unit grid, inlined by `concepts.py`
     so the page stays one self-contained file. */
  const conceptById = {};
  (DATA.concepts || []).forEach((concept) => {
    conceptById[concept.id] = concept;
  });

  function conceptOf(artifactOrId) {
    const artifact =
      typeof artifactOrId === "string"
        ? artifactById[artifactOrId]
        : artifactOrId;
    return artifact ? conceptById[artifact.concept] || null : null;
  }

  /* An icon for an HTML flow, and one for an SVG scene. Both take the path
     data rather than a concept, so a caller that already resolved the concept
     does not resolve it twice. */
  function glyph(path, cls) {
    if (!path) return null;
    const node = svg("svg", {
      class: cls || "glyph",
      viewBox: "0 0 24 24",
      "aria-hidden": "true",
      focusable: "false",
    });
    node.appendChild(svg("path", { d: path }));
    return node;
  }

  function sceneGlyph(path, x, y, size, cls) {
    if (!path) return null;
    const group = svg("g", {
      class: cls || "cglyph",
      transform: "translate(" + x + "," + y + ") scale(" + size / 24 + ")",
      "aria-hidden": "true",
    });
    group.appendChild(svg("path", { d: path }));
    return group;
  }

  // The step note builds its rows as markup, so the same mark is needed as a
  // string. Path data is authored in `concepts.py`, but it still goes through
  // the escape used for everything else that reaches innerHTML.
  function glyphHtml(path, cls) {
    if (!path) return "";
    return (
      '<svg class="' +
      escapeHtml(cls || "glyph") +
      '" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="' +
      escapeHtml(path) +
      '"/></svg>'
    );
  }

  /* A list of artifacts, each behind its concept's glyph and titled with the
     concept it belongs to. */
  function artifactList(ids) {
    return (ids || [])
      .map((id) => {
        const artifact = artifactById[id];
        if (!artifact) return escapeHtml(id);
        const concept = conceptOf(artifact);
        return (
          '<span class="artifact-ref"' +
          (concept ? ' title="' + escapeHtml(concept.label) + '"' : "") +
          ">" +
          (concept ? glyphHtml(concept.path) : "") +
          escapeHtml(artifact.label) +
          "</span>"
        );
      })
      .join(", ");
  }

  // Which concern a step belongs to, and therefore which column it is aligned
  // in. Validated in spec.py to claim each step at most once.
  const groupById = {};
  const groupOfStep = {};
  (DATA.groups || []).forEach((group) => {
    groupById[group.id] = group;
    (group.steps || []).forEach((stepId) => {
      groupOfStep[stepId] = group.id;
    });
  });

  function kindColor(kind) {
    return "var(--kind-" + kind + ")";
  }

  // The payload arrives with its keys sorted, so every place that shows the
  // kinds—the legend, the filter row, the teaser figure—reads them through
  // here and gets the one authored reading order.
  function kindEntries() {
    return Object.keys(DATA.kinds)
      .sort(function (a, b) {
        return DATA.kinds[a].order - DATA.kinds[b].order;
      })
      .map(function (kind) {
        return [kind, DATA.kinds[kind]];
      });
  }

  /* -------------------------------------------------- pipeline chart */

  /* One interactive chart, mounted into `host` and owning its own selection.

     Everything from here to the end of `createChart` is per-instance: the two
     pipelines are drawn side by side in the document, and a selection in one
     must not redraw the other. The layout itself is unchanged—the layer rule,
     the group blocks and the edge routing are the same code that drew the
     single tabbed chart—it simply closes over an instance `state` and instance
     DOM nodes instead of the page's.

     `options.size` picks the level of detail—"mid" or "compact". Compact drops
     everything written inside a node but its name; both are scaled to the
     column rather than scrolled sideways. What they drop is detail, never
     structure—the reader still sees every step, every dependency and every
     band with its label. */
  function createChart(host, laneId, figureNumber, options) {
    const settings = options || {};
    const size = settings.size || "mid";
    const M = METRICS[size];
    // Asked of the size often enough to name: whether the node carries only
    // the step's name.
    const compact = size === "compact";
    // Declared up front so `select` can name the instance the step note belongs to
    // before the instance is finished being built.
    const instance = {
      lane: laneId,
      figure: figureNumber,
      size: size,
      host: host,
    };
    const state = {
      tab: laneId,
      selected: null,
    };

    const lane = DATA.lanes[laneId];
    const wrapCache = {}; // step id → the lines a node prints
    let naturalSize = null; // the drawing's own size, in SVG user units
    const flow = svg("svg", {
      class: "flow flow-reduced flow-" + size,
      role: "img",
      "aria-label": "Flow chart of the " + lane.label + " pipeline",
    });
    // Named for the element rather than for the helper, which the drawing
    // routine below calls to refill it.
    const captionNode = el("figcaption", { class: "cap cap-figure" });

    function stepsInTab() {
      return DATA.steps.filter((step) => {
        return step.column === state.tab;
      });
    }

    /* ------------------------------------------------------------ chart */

    /* A step's dependencies as the spec declares them, one edge per parent. */
    function directDeps(step) {
      const out = [];
      const taken = new Set();
      (step.depends_on || []).forEach((dep) => {
        if (!stepById[dep.on] || taken.has(dep.on)) return;
        taken.add(dep.on);
        out.push({ from: dep.on, data: dep.data });
      });
      return out;
    }

    function buildGraph() {
      const steps = stepsInTab();

      const parents = {};
      steps.forEach((step) => {
        parents[step.id] = directDeps(step);
      });

      // Layer = longest dependency path, so nothing is ever drawn above
      // something it reads. The spec is validated acyclic, so this terminates.
      const layerOf = {};
      function layer(id) {
        if (layerOf[id] !== undefined) return layerOf[id];
        layerOf[id] = 0;
        let best = 0;
        (parents[id] || []).forEach((edge) => {
          best = Math.max(best, layer(edge.from) + 1);
        });
        layerOf[id] = best;
        return best;
      }
      steps.forEach((step) => {
        layer(step.id);
      });

      return {
        steps: steps,
        parents: parents,
        layerOf: layerOf,
      };
    }

    /* A group is only aligned where it is actually continuous. The layers a group
       occupies are cut into runs of consecutive layers, and each run becomes one
       rigid block: the portrait sits four layers below the last image step, with
       unrelated work in between, so it is placed on its own rather than dragged
       into the imagery strand and stretching a band over the gap. A run of one
       step is no group at all—nothing to align, nothing to band. */
    function buildBlocks(rows) {
      const runOfLayer = {};
      const layersOf = {};
      rows.forEach((row, layer) => {
        row.forEach((node) => {
          const groupId = groupOfStep[node.id] || null;
          if (!groupId) return;
          (layersOf[groupId] = layersOf[groupId] || []).push(layer);
        });
      });
      Object.keys(layersOf).forEach((groupId) => {
        const layers = layersOf[groupId]
          .filter((layer, index, all) => {
            return all.indexOf(layer) === index;
          })
          .sort((a, b) => {
            return a - b;
          });
        const runs = {};
        let run = 0;
        layers.forEach((layer, index) => {
          if (index && layer !== layers[index - 1] + 1) run += 1;
          runs[layer] = run;
        });
        runOfLayer[groupId] = runs;
      });

      const blocks = [];
      const byKey = {};
      rows.forEach((row, layer) => {
        row.forEach((node, index) => {
          const groupId = groupOfStep[node.id] || null;
          const key = groupId
            ? "g:" + groupId + ":" + runOfLayer[groupId][layer]
            : "n:" + node.id;
          let block = byKey[key];
          if (!block) {
            block = {
              group: groupId ? groupById[groupId] : null,
              members: [],
              byLayer: {},
              layers: [],
              first: layer,
              rank: 0,
              cx: 0,
              links: [], // the edges leaving the block, one entry per edge end
            };
            byKey[key] = block;
            blocks.push(block);
          }
          node.block = block;
          block.members.push(node);
          if (!block.byLayer[layer]) {
            block.byLayer[layer] = [];
            block.layers.push(layer);
          }
          block.byLayer[layer].push(node);
          // Where the barycenter pass put this node in its row, normalized, so a
          // block keeps the side of the chart its members were ordered onto.
          block.rank += row.length > 1 ? index / (row.length - 1) : 0.5;
        });
      });

      blocks.forEach((block) => {
        block.rank /= block.members.length;
        // Wide enough for its busiest layer, so the block is one rigid rectangle.
        block.width = block.layers.reduce((best, layer) => {
          const list = block.byLayer[layer];
          return Math.max(
            best,
            list.reduce((sum, node) => {
              return sum + node.w;
            }, 0) +
              M.COL_GAP * (list.length - 1)
          );
        }, 0);
        // Where each member's center sits relative to the block's: the members
        // of one layer are centered on the block, so the offset is fixed by the
        // block's shape and the placement only ever moves the block.
        block.layers.forEach((layer) => {
          const list = block.byLayer[layer];
          const total =
            list.reduce((sum, node) => {
              return sum + node.w;
            }, 0) +
            M.COL_GAP * (list.length - 1);
          let x = -total / 2;
          list.forEach((node) => {
            node.offset = x + node.w / 2;
            x += node.w + M.COL_GAP;
          });
        });
        if (block.members.length < 2) block.group = null;
      });
      // One order for the whole chart, so a block that spans layers cannot be
      // asked to sit left of something in one layer and right of it in another.
      blocks.sort((a, b) => {
        return a.rank - b.rank || a.first - b.first;
      });
      return blocks;
    }

    /* Horizontal placement, in two stages. The layer decides how far *down* a
       node goes; the graph says nothing about how far across, and that freedom is
       spent on meaning—the steps of one concern are aligned so they read as a
       single vertical strand—and on short edges.

       Stage one places the blocks: group runs and lone nodes alike, each a rigid
       rectangle with one x for every layer it crosses. Positions are continuous,
       not slots in a grid. A leftmost packing gives a feasible start and fixes
       the chart's width, since every block is then as far left as it can go.
       Inside that width, the blocks are moved to minimize the summed squared
       horizontal offset of the edges, each measured between the centers of the
       two steps it joins. A block is pulled to the mean of the positions its
       edges ask for and clamped to the room its neighbors in every layer it
       occupies leave, so the arrangement stays valid at every step. Two blocks
       that jam against each other—one pulled toward the other, which has
       nowhere to go on its own—are then moved as one, by their edges to the
       rest of the chart; otherwise a strand fed from one side would stay
       pressed against the margin because the strand beside it holds it there.

       Stage two places the nodes inside each block, centered on it, which is what
       makes a group's steps line up: a run with one step per layer puts every
       step at the same x. */
    function arrange(rows, graph) {
      const blocks = buildBlocks(rows);
      if (!blocks.length) return { blocks: blocks, width: M.NODE_W };

      const perLayer = rows.map(() => {
        return [];
      });
      blocks.forEach((block) => {
        block.layers.forEach((layer) => {
          perLayer[layer].push(block);
        });
      });

      const nodeById = {};
      rows.forEach((row) => {
        row.forEach((node) => {
          nodeById[node.id] = node;
        });
      });
      // An edge inside a block never changes length, so only the ones between
      // blocks pull. Each is recorded at both ends, as the offset the near end
      // has inside its block and the far end's node.
      graph.steps.forEach((step) => {
        (graph.parents[step.id] || []).forEach((edge) => {
          const from = nodeById[edge.from];
          const to = nodeById[step.id];
          if (!from || !to || from.block === to.block) return;
          from.block.links.push({ offset: from.offset, other: to });
          to.block.links.push({ offset: to.offset, other: from });
        });
      });
      function gap(left, right) {
        return (left.width + right.width) / 2 + M.COL_GAP;
      }
      function centerOf(node) {
        return node.block.cx + node.offset;
      }
      // The x the block's edges ask for: where its center would have to be for
      // each edge to run straight, averaged.
      function target(block) {
        return (
          block.links.reduce((sum, link) => {
            return sum + centerOf(link.other) - link.offset;
          }, 0) / block.links.length
        );
      }

      // Leftmost feasible packing. Pushing one block right can invalidate a layer
      // already packed, so the sweep repeats until nothing moves; it only ever
      // increases x, so it terminates.
      let moved = true;
      let guard = 0;
      while (moved && guard < blocks.length + 4) {
        moved = false;
        guard += 1;
        perLayer.forEach((list) => {
          list.forEach((block, index) => {
            const min = index
              ? list[index - 1].cx + gap(list[index - 1], block)
              : block.width / 2;
            if (block.cx < min - 0.01) {
              block.cx = min;
              moved = true;
            }
          });
        });
      }
      // The packing is as narrow as the order allows, and the chart stays that
      // wide: nothing below moves a block past its right edge.
      const extent = blocks.reduce((best, block) => {
        return Math.max(best, block.cx + block.width / 2);
      }, 0);

      // The room a set of blocks has either side, from the nearest block outside
      // the set in any layer a member occupies, or from the chart's edge.
      function room(set) {
        let left = Infinity;
        let right = Infinity;
        set.forEach((block) => {
          left = Math.min(left, block.cx - block.width / 2);
          right = Math.min(right, extent - block.width / 2 - block.cx);
          block.layers.forEach((layer) => {
            const list = perLayer[layer];
            const index = list.indexOf(block);
            const before = list[index - 1];
            const after = list[index + 1];
            if (before && set.indexOf(before) === -1) {
              left = Math.min(left, block.cx - before.cx - gap(before, block));
            }
            if (after && set.indexOf(after) === -1) {
              right = Math.min(right, after.cx - block.cx - gap(block, after));
            }
          });
        });
        return { left: Math.max(0, left), right: Math.max(0, right) };
      }
      const EPS = 0.01;

      // Relax. A block may move only inside the room its neighbors leave, so the
      // arrangement stays valid; alternating the sweep direction keeps the result
      // from leaning the way it was traversed. Every move shortens the edges, so
      // the passes settle, and the guard only bounds the cost of one drawing.
      for (let pass = 0; pass < 60; pass += 1) {
        moved = false;
        const order = pass % 2 ? blocks.slice().reverse() : blocks;
        order.forEach((block) => {
          if (!block.links.length) return;
          const free = room([block]);
          const next = Math.min(
            Math.max(target(block), block.cx - free.left),
            block.cx + free.right
          );
          if (Math.abs(next - block.cx) > EPS) {
            block.cx = next;
            moved = true;
          }
        });

        // Blocks that are jammed: a block still pulled past a neighbor it already
        // touches is joined with that neighbor, transitively, and the set is moved
        // by the edges that leave it, as far as the room around the set allows.
        const setOf = new Map();
        blocks.forEach((block) => {
          setOf.set(block, [block]);
        });
        function join(a, b) {
          const setA = setOf.get(a);
          const setB = setOf.get(b);
          if (setA === setB) return;
          setB.forEach((block) => {
            setA.push(block);
            setOf.set(block, setA);
          });
        }
        blocks.forEach((block) => {
          if (!block.links.length) return;
          const pull = target(block) - block.cx;
          if (Math.abs(pull) <= EPS) return;
          block.layers.forEach((layer) => {
            const list = perLayer[layer];
            const index = list.indexOf(block);
            const next = pull > 0 ? list[index + 1] : list[index - 1];
            if (!next) return;
            const touching =
              pull > 0
                ? next.cx - block.cx - gap(block, next) <= EPS
                : block.cx - next.cx - gap(next, block) <= EPS;
            if (touching) join(block, next);
          });
        });
        const seen = new Set();
        blocks.forEach((block) => {
          const set = setOf.get(block);
          if (seen.has(set) || set.length < 2) return;
          seen.add(set);
          let sum = 0;
          let count = 0;
          set.forEach((member) => {
            member.links.forEach((link) => {
              if (set.indexOf(link.other.block) !== -1) return;
              sum += centerOf(link.other) - link.offset - member.cx;
              count += 1;
            });
          });
          if (!count) return;
          const free = room(set);
          const shift = Math.min(Math.max(sum / count, -free.left), free.right);
          if (Math.abs(shift) <= EPS) return;
          set.forEach((member) => {
            member.cx += shift;
          });
          moved = true;
        });
        if (!moved) break;
      }

      let left = Infinity;
      let right = -Infinity;
      blocks.forEach((block) => {
        left = Math.min(left, block.cx - block.width / 2);
        right = Math.max(right, block.cx + block.width / 2);
      });
      const origin = M.PAD + M.RAIL_W + M.MARGIN_CH - left;
      blocks.forEach((block) => {
        block.cx += origin;
        // Stage two: the members of one layer, centered on the block.
        block.members.forEach((node) => {
          node.px = block.cx + node.offset - node.w / 2;
        });
      });

      return { blocks: blocks, width: Math.max(M.NODE_W, right - left) };
    }

    /* The band behind a group run, drawn around the whole rigid block rather than
       around the members, so it stays a clean rectangle in layers where the run
       has only one step. */
    function groupBands(blocks) {
      const bands = [];
      blocks.forEach((block) => {
        if (!block.group) return;
        let y0 = Infinity;
        let y1 = -Infinity;
        block.members.forEach((node) => {
          y0 = Math.min(y0, node.y);
          y1 = Math.max(y1, node.y + node.h);
        });
        bands.push({
          group: block.group,
          count: block.members.length,
          x0: block.cx - block.width / 2 - M.BAND_PAD,
          x1: block.cx + block.width / 2 + M.BAND_PAD,
          y0: y0 - M.BAND_HEAD,
          y1: y1 + M.BAND_PAD,
        });
      });
      return bands;
    }

    function layout() {
      const graph = buildGraph();
      const rows = [];

      function rowFor(index) {
        while (rows.length <= index) rows.push([]);
        return rows[index];
      }

      graph.steps.forEach((step) => {
        rowFor(graph.layerOf[step.id]).push({
          type: "step",
          id: step.id,
          step: step,
          w: M.NODE_W,
          h: M.NODE_H,
          order: step._order,
        });
      });
      // Two barycenter passes: order each row by the average position of its
      // parents, which is enough to untangle graphs this small.
      const indexOf = {};
      function reindex() {
        rows.forEach((row) => {
          row.forEach((node, index) => {
            indexOf[node.id] = index;
          });
        });
      }
      rows.forEach((row) => {
        row.sort((a, b) => {
          return a.order - b.order;
        });
      });
      reindex();
      for (let pass = 0; pass < 2; pass += 1) {
        rows.forEach((row) => {
          row.forEach((node) => {
            const upstream = (graph.parents[node.id] || []).map((edge) => {
              return indexOf[edge.from];
            });
            const known = upstream.filter((value) => {
              return value !== undefined;
            });
            node.bary = known.length
              ? known.reduce((sum, value) => {
                  return sum + value;
                }, 0) / known.length
              : indexOf[node.id];
          });
          row.sort((a, b) => {
            return a.bary - b.bary || a.order - b.order;
          });
        });
        reindex();
      }

      const placement = arrange(rows, graph);
      const contentW = placement.width;

      const nodes = [];
      const byId = {};
      const rails = [];
      let y = M.HEAD_H;
      rows.forEach((row, index) => {
        const rowH = row.reduce((best, node) => {
          return Math.max(best, node.h);
        }, 0);
        row.forEach((node) => {
          node.x = node.px;
          node.y = y;
          node.layer = index;
          nodes.push(node);
          byId[node.id] = node;
        });
        // Blocks are ordered once for the whole chart, which can differ from the
        // barycenter order inside a single row; the edge fanning and the channel
        // search below both read rows left to right.
        row.sort((a, b) => {
          return a.x - b.x;
        });
        rails.push({ label: String(index + 1), y0: y, y1: y + rowH });
        y += rowH + M.LAYER_GAP;
      });

      const bands = groupBands(placement.blocks);

      // Edges leave and enter along the node's edge, fanned out and sorted by the
      // other end's position so parallel links do not cross inside a gap.
      const edges = [];
      graph.steps.forEach((step) => {
        (graph.parents[step.id] || []).forEach((edge) => {
          if (!byId[edge.from] || !byId[step.id]) return;
          edges.push({
            from: byId[edge.from],
            to: byId[step.id],
            data: edge.data,
          });
        });
      });

      const outgoing = {};
      const incoming = {};
      edges.forEach((edge) => {
        (outgoing[edge.from.id] = outgoing[edge.from.id] || []).push(edge);
        (incoming[edge.to.id] = incoming[edge.to.id] || []).push(edge);
      });
      Object.values(outgoing).forEach((list) => {
        list.sort((a, b) => {
          return a.to.x - b.to.x;
        });
        list.forEach((edge, index) => {
          edge.x1 =
            edge.from.x + (edge.from.w * (index + 1)) / (list.length + 1);
          edge.y1 = edge.from.y + edge.from.h;
        });
      });
      Object.values(incoming).forEach((list) => {
        list.sort((a, b) => {
          return a.from.x - b.from.x;
        });
        list.forEach((edge, index) => {
          edge.x2 = edge.to.x + (edge.to.w * (index + 1)) / (list.length + 1);
          edge.y2 = edge.to.y;
        });
      });

      routeLongEdges(edges, rows, contentW, bands);

      return {
        nodes: nodes,
        edges: edges,
        rails: rails,
        bands: bands,
        layers: rows.length,
        width: M.PAD * 2 + M.RAIL_W + M.MARGIN_CH * 2 + contentW,
        height: (rows.length ? y - M.LAYER_GAP : M.HEAD_H) + M.PAD,
      };
    }

    /* An edge that skips a layer would otherwise be drawn straight through the
       nodes in between. Each one is given a vertical channel—a column of empty
       space free across every layer it crosses—and routed down it. A group's
       band counts as occupied even where its column is empty: a line running
       down the middle of a band would read as belonging to it. */
    function routeLongEdges(edges, rows, contentW, bands) {
      const left = M.PAD + M.RAIL_W;
      const right = left + M.MARGIN_CH * 2 + contentW;
      // The side channels hug the very edge: with the relaxation free to push a
      // block flush against the left of the content, anything further in is inside
      // the clearance of the leftmost node and gets rejected in every row.
      const margins = [left + 9, right - 9];
      const candidates = margins.slice();
      rows.forEach((row) => {
        row.forEach((node, index) => {
          if (index === 0) return;
          const previous = row[index - 1];
          candidates.push((previous.x + previous.w + node.x) / 2);
        });
      });

      const taken = [];
      edges
        .filter((edge) => {
          return edge.to.layer - edge.from.layer > 1;
        })
        .sort((a, b) => {
          return b.to.layer - b.from.layer - (a.to.layer - a.from.layer);
        })
        .forEach((edge) => {
          const crossed = [];
          for (
            let index = edge.from.layer + 1;
            index < edge.to.layer;
            index += 1
          ) {
            crossed.push(rows[index]);
          }
          const midpoint = (edge.x1 + edge.x2) / 2;
          const usable = candidates
            .filter((x) => {
              return crossed.every((row) => {
                return row.every((node) => {
                  return x < node.x - 18 || x > node.x + node.w + 18;
                });
              });
            })
            .filter((x) => {
              return !(bands || []).some((band) => {
                return (
                  x > band.x0 - 2 &&
                  x < band.x1 + 2 &&
                  band.y0 < edge.y2 &&
                  edge.y1 < band.y1
                );
              });
            })
            .filter((x) => {
              return !taken.some((used) => {
                return (
                  Math.abs(used.x - x) < 10 &&
                  used.y0 < edge.y2 &&
                  edge.y1 < used.y1
                );
              });
            })
            .sort((a, b) => {
              return Math.abs(a - midpoint) - Math.abs(b - midpoint);
            });
          if (!usable.length) {
            // Nothing free. A short skip is still readable drawn straight; one
            // that crosses the whole chart is not, and cutting it through a band
            // would read as belonging to that group—so it takes the near margin
            // and shares it rather than going through the middle.
            if (edge.to.layer - edge.from.layer < 3) return;
            edge.channel =
              Math.abs(margins[0] - midpoint) <= Math.abs(margins[1] - midpoint)
                ? margins[0]
                : margins[1];
            return;
          }
          edge.channel = usable[0];
          taken.push({ x: edge.channel, y0: edge.y1, y1: edge.y2 });
        });
    }

    /* The band is ground: it goes down before the edges and the nodes. Its label
       goes on last, in `drawBandLabels`, or the arrows into the group's first step
       would be drawn across it. */
    function drawBandAreas(root, bands) {
      bands.forEach((band) => {
        const group = svg("g", { class: "band" });
        group.appendChild(
          svg("rect", {
            class: "band-area",
            x: band.x0,
            y: band.y0,
            width: band.x1 - band.x0,
            height: band.y1 - band.y0,
            rx: 8,
          })
        );
        const tip = svg("title");
        tip.textContent =
          band.group.label +
          "—" +
          band.count +
          " consecutive steps of one concern, aligned" +
          (band.group.note ? "\n" + band.group.note : "");
        group.appendChild(tip);
        root.appendChild(group);
      });
    }

    /* The phase's name, in the band's head, at both sizes: a compact figure
       that showed the bands without naming them left the reader to guess what
       the prose's phases were. Its box is sized from the character count, in
       the size's own units, so the label never runs past the band. */
    function drawBandLabels(root, bands) {
      bands.forEach((band) => {
        const text = truncateLabel(band.group.label, 30);
        root.appendChild(
          svg("rect", {
            class: "band-label-bg",
            x: band.x0 + 7,
            y: band.y0 + 2,
            width: text.length * M.BAND_LABEL_CH + 12,
            height: M.BAND_LABEL_H,
            rx: 3,
          })
        );
        const label = svg("text", {
          class: "band-label",
          x: band.x0 + 13,
          y: band.y0 + M.BAND_LABEL_DY,
        });
        label.textContent = text;
        root.appendChild(label);
      });
    }

    function drawRails(root, rails) {
      const x = M.PAD + M.RAIL_W - M.RAIL_GAP;
      rails.forEach((rail) => {
        root.appendChild(
          svg("path", {
            class: "rail-rule",
            d: "M" + x + " " + rail.y0 + " L" + x + " " + rail.y1,
          })
        );
        const label = svg("text", {
          class: "rail-label",
          x: x - M.RAIL_DX,
          y: rail.y0 + M.RAIL_DY,
          "text-anchor": "end",
        });
        label.textContent = rail.label;
        root.appendChild(label);
      });
    }

    function edgeActive(edge) {
      if (!state.selected) return false;
      return edge.from.id === state.selected || edge.to.id === state.selected;
    }

    function edgePath(edge) {
      const end = edge.y2 - 7;
      if (edge.channel === undefined) {
        const bend = Math.max(14, (end - edge.y1) * 0.45);
        return (
          "M" +
          edge.x1 +
          " " +
          edge.y1 +
          " C" +
          edge.x1 +
          " " +
          (edge.y1 + bend) +
          ", " +
          edge.x2 +
          " " +
          (end - bend) +
          ", " +
          edge.x2 +
          " " +
          end
        );
      }
      const knee = 22;
      const enter = edge.y1 + knee * 2;
      const leave = end - knee * 2;
      return (
        "M" +
        edge.x1 +
        " " +
        edge.y1 +
        " C" +
        edge.x1 +
        " " +
        (edge.y1 + knee) +
        ", " +
        edge.channel +
        " " +
        (enter - knee) +
        ", " +
        edge.channel +
        " " +
        enter +
        " L" +
        edge.channel +
        " " +
        leave +
        " C" +
        edge.channel +
        " " +
        (leave + knee) +
        ", " +
        edge.x2 +
        " " +
        (end - knee) +
        ", " +
        edge.x2 +
        " " +
        end
      );
    }

    function drawEdges(root, edges) {
      edges.forEach((edge) => {
        const active = edgeActive(edge);
        const path = svg("path", {
          class: "edge" + (active ? " active" : ""),
          d: edgePath(edge),
        });
        const tip = svg("title");
        tip.textContent = edge.data
          ? edge.data + (edge.indirect ? " (via a hidden step)" : "")
          : "data flow";
        path.appendChild(tip);
        root.appendChild(path);
        root.appendChild(
          svg("path", {
            class: "edge-arrow" + (active ? " active" : ""),
            d:
              "M" +
              (edge.x2 - 4) +
              " " +
              (edge.y2 - 7) +
              " L" +
              (edge.x2 + 4) +
              " " +
              (edge.y2 - 7) +
              " L" +
              edge.x2 +
              " " +
              edge.y2 +
              " Z",
          })
        );
      });
    }

    function drawNode(root, node) {
      const step = node.step;
      const group = svg("g", {
        class: "node" + (state.selected === step.id ? " selected" : ""),
        transform: "translate(" + node.x + "," + node.y + ")",
        tabindex: "0",
        role: "button",
        "aria-label": step.label + "—" + DATA.kinds[step.kind].label,
      });

      group.appendChild(
        svg("rect", { class: "body", width: node.w, height: node.h })
      );
      // Kind accent: a color bar plus the kind's name in the fact line below,
      // so the kind is never signaled by color alone.
      group.appendChild(
        svg("rect", {
          x: 0,
          y: 0,
          width: 4,
          height: node.h,
          fill: kindColor(step.kind),
        })
      );

      /* A node carries the step's name, wrapped, and at mid the one line that
         says what kind of step it is and which model it calls.

         Compact stops at the name deliberately. The script, the kind and the
         model are one line of small type each, and three of those in a
         104-unit box is a grey block rather than a label. What is left out of
         either is still on the node—in its tooltip and its accessible name—and
         set out in full in the step note. */
      {
        // Measured once per step: the node's width never changes within an
        // instance, and `draw` runs again on every selection.
        if (!wrapCache[step.id]) {
          wrapCache[step.id] = fitLines(
            root,
            step.label,
            node.w - M.LABEL_PAD * 2,
            M.LABEL_LINES
          );
        }
        const lines = wrapCache[step.id];
        // The name is centred in what the fact line leaves it, so a one-line
        // name sits where a two-line one would, rather than floating high.
        const room = node.h - M.FACT_UP * 2;
        const top = room / 2 - ((lines.length - 1) * M.LINE_H) / 2 + 3;
        lines.forEach((line, index) => {
          const text = svg("text", {
            class: "title",
            x: M.LABEL_PAD,
            y: top + index * M.LINE_H,
          });
          text.textContent = line;
          group.appendChild(text);
        });

        if (M.FACT_UP) {
          // The kind alone names nothing for a step that calls no model, so
          // such a step prints its byline instead: the service it asks, the
          // rule it applies. The color bar still carries the kind.
          const facts = [step.byline || DATA.kinds[step.kind].label];
          // The model before the per-run marker, so that a line the node has
          // to cut loses the marker rather than the model.
          if (step.model) facts.push(step.model.split(" (")[0]);
          if (step.calls_per_run && step.calls_per_run !== "1")
            facts.push("×N");
          const factLine = svg("text", {
            class: "metric",
            x: M.LABEL_PAD,
            y: node.h - M.FACT_UP,
          });
          factLine.textContent = fitLines(
            root,
            facts.join(" · "),
            node.w - M.LABEL_PAD * 2,
            1,
            "metric"
          )[0];
          group.appendChild(factLine);
        }

        const tip = svg("title");
        tip.textContent =
          step.label +
          "\n" +
          DATA.kinds[step.kind].label +
          "\n" +
          step.script +
          (step.model ? "\n" + step.model.split(" (")[0] : "");
        group.appendChild(tip);
        bindNode(group, step);
        root.appendChild(group);
      }
    }

    function bindNode(group, step) {
      group.addEventListener("click", () => {
        select(step.id);
      });
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select(step.id);
        }
      });
    }

    /* How large to render a reduced drawing, given the room it has.

       The width it is given is a hard limit—a reduced chart that scrolls
       sideways has failed at its one job—while the viewport's height and the
       ceiling only hold it back, and the floor stops a short window shrinking
       it away. */
    function refit() {
      if (!naturalSize) return;
      const available = (host && host.clientWidth) || naturalSize.width;
      // `fitScale` reads the largest pipeline, so the meta graph comes out
      // smaller than the personal one because it is smaller—not because it was
      // fitted to the same column on its own. Sized per figure, a narrow column
      // would set the shorter graph 40% larger than its neighbour and quietly
      // deny the comparison the prose promises.
      const scale = fitScale(size, available);
      flow.style.width = Math.round(naturalSize.width * scale) + "px";
    }

    function draw() {
      const host = flow;
      clear(host);

      const geometry = layout();
      host.setAttribute(
        "viewBox",
        "0 0 " + geometry.width + " " + geometry.height
      );
      host.setAttribute("width", geometry.width);
      host.setAttribute("height", geometry.height);
      // The drawing must never scroll sideways—that is the whole point of it—so
      // it is given no minimum and the stylesheet fits it to the column.
      naturalSize = { width: geometry.width, height: geometry.height };
      refit();
      host.setAttribute(
        "aria-label",
        "Dependency graph of the " + DATA.lanes[state.tab].label + " pipeline"
      );

      drawBandAreas(host, geometry.bands);
      drawRails(host, geometry.rails);
      drawEdges(host, geometry.edges);
      geometry.nodes.forEach((node) => {
        drawNode(host, node);
      });
      drawBandLabels(host, geometry.bands);

      /* What the figure is, and then the marks that carry no label of their
         own. The layer semantics, the branch structure and what a step node
         prints belong to the prose and to the drawing itself, and a caption
         that repeated them argued with both. A mark is named only when it is
         actually drawn. */
      const marks = [
        compact ? "The color bar gives the step kind." : "",
        geometry.bands.length
          ? "A shaded band gathers the steps of one phase."
          : "",
      ];

      fillCaption(
        captionNode,
        "Figure",
        figureNumber,
        [DATA.lanes[state.tab].label + " pipeline as a dependency graph."]
          .concat(marks.filter(Boolean))
          .join(" ")
      );
      // A redraw replaces the node the note is anchored to, so the note is
      // placed again against what is drawn now.
      placeStepTip();
    }

    /* ------------------------------------------------------------- mount */

    function select(stepId) {
      if (!stepById[stepId]) return;
      state.selected = stepId;
      markStepRefs(stepId);
      // Drawn first: the note is anchored to the selected node, which exists
      // only once the figure has been redrawn with the selection.
      draw();
      openStepTip(stepById[stepId], instance);
    }

    /* Measuring only: the caller wants to know how much room this pipeline's
       drawing needs at this size, and no chart is mounted. The layout is
       arithmetic over the spec—no text is measured, nothing is appended—so
       asking is cheap, and it is the only honest way to size the figure. */
    if (settings.measure) {
      const geometry = layout();
      return { width: geometry.width, height: geometry.height };
    }

    host.appendChild(
      el("figure", { class: "figure" }, [
        captionNode,
        el("div", { class: "chart-scroll" }, [flow]),
      ])
    );

    draw();

    // Prose points into the figure: `[[step:id]]` compiles to a control that
    // selects a node this chart owns, exactly as pressing the node does.
    instance.select = select;
    instance.selected = function () {
      return state.selected;
    };
    instance.clearSelection = function () {
      if (state.selected === null) return;
      state.selected = null;
      markStepRefs(null);
      draw();
    };
    // Re-fitting is not re-drawing: the layout is unchanged, only the size the
    // finished drawing is rendered at, so a resize costs one style write.
    instance.refit = refit;
    // A chart can be replaced—the page crossing into the compact size—and a
    // dead instance left in `charts` would go on drawing into a detached node
    // every time the step note cleared the other selection.
    instance.destroy = function () {
      const index = charts.indexOf(instance);
      if (index !== -1) charts.splice(index, 1);
      clear(host);
    };
    charts.push(instance);
    return instance;
  }

  /* --------------------------------------------------- references into a chart */

  /* A reference into a figure is a span with a button's role rather than a
     button: a button is an atomic inline whatever its display says, so a phrase
     in one could not break across lines and would move to the next line whole.
     A span has none of a button's keyboard, so Enter and Space are given back
     here, once for every kind of reference, by turning them into the click the
     handlers below already listen for. */
  function bindRefKeys() {
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const target = event.target;
      if (!target || !target.classList || !target.classList.contains("figref"))
        return;
      event.preventDefault();
      target.click();
    });
  }

  /* A `[[step:id]]` in the prose compiles to a `.figref` carrying the step and
     the pipeline it is drawn in, and pressing it does what pressing the node
     does: the step is selected in the figure and its note opens on it. This
     is what lets an account of what a pipeline does name its steps without
     restating them—the sentence says why the step is there, and the figure and
     the note keep what it is, which model it calls and what it reads. */

  function chartForLane(laneId) {
    return (
      charts.find((chart) => {
        return chart.lane === laneId && chart.host;
      }) || null
    );
  }

  /* Bring the selected node into view. Two scrolls, because a chart sits in two
     of them: the page, which the figure may be off, and the figure's own
     scroller, kept in case a drawing ever outgrows its box. */
  function revealStep(chart) {
    const node = chart.host && chart.host.querySelector(".node.selected");
    if (!node) return;
    const scroller = node.closest ? node.closest(".chart-scroll") : null;
    if (scroller) {
      const box = node.getBoundingClientRect();
      const frame = scroller.getBoundingClientRect();
      const dx = box.left + box.width / 2 - (frame.left + frame.width / 2);
      if (Math.abs(dx) > 4) scroller.scrollLeft += dx;
    }
    const figure = chart.host.closest ? chart.host.closest(".widget") : null;
    const target = figure || chart.host;
    const box = target.getBoundingClientRect();
    const viewport =
      window.innerHeight || document.documentElement.clientHeight;
    if (box.top < 0 || box.bottom > viewport) {
      target.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  function markStepRefs(stepId) {
    Array.prototype.forEach.call(
      document.querySelectorAll(".figref[data-step]"),
      (node) => {
        const lit = !!stepId && node.getAttribute("data-step") === stepId;
        node.classList.toggle("is-lit", lit);
        node.setAttribute("aria-expanded", lit ? "true" : "false");
      }
    );
  }

  function bindStepRefs() {
    document.addEventListener("click", (event) => {
      const ref = event.target.closest
        ? event.target.closest(".figref[data-step]")
        : null;
      if (!ref) return;
      event.preventDefault();
      const chart = chartForLane(ref.getAttribute("data-lane"));
      // No chart on the page—a viewport too narrow to mount one, or a build
      // that drew the other pipeline only—leaves the phrase as the prose it
      // already reads as.
      if (!chart) return;
      const stepId = ref.getAttribute("data-step");
      if (chart.selected() === stepId) {
        closeStepTip();
        return;
      }
      chart.select(stepId);
      revealStep(chart);
    });
  }

  /* --------------------------------------------------------- step entry */

  function factRow(label, value) {
    if (!value) return null;
    return el("tr", {}, [el("th", { text: label }), el("td", { html: value })]);
  }

  function dependencyList(step) {
    return (step.depends_on || [])
      .map((dep) => {
        const parent = stepById[dep.on];
        return (
          "<b>" +
          escapeHtml(parent ? parent.label : dep.on) +
          "</b>—" +
          escapeHtml(dep.data)
        );
      })
      .join("<br>");
  }

  /* A resolved value arrives as `gpt-5 (env OPENAI_MODEL)`: the value, then
     where the scan found it. The record prints the value alone; where it was
     resolved from is how the source is read, which the record leaves to the
     source. */
  function bare(value) {
    return String(value).split(" (")[0].trim();
  }

  /* The record an entry prints beside its description, each value as markup.
     Two readers use it. The step note lays it out as a two-column table for one
     step at a time, and the print appendix as the columns of one table with a
     row per step, so both say the same thing about a step.

     The record is short by design. Input and output are the phrases the
     summarizer wrote from the source, in the vocabulary of the figures; a
     hand-written fallback entry has none, so the declared dependencies and
     artifacts stand in. Model, reasoning effort, and calls per run are
     measured from the code. Everything else about a step—its file and line,
     its output schema, the flag that skips it—is source, and the figures
     index the source rather than copying it. */
  // A written input or output is a phrase; a cell opens with a capital.
  function initialCapital(text) {
    return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
  }

  function stepRecord(step) {
    const summary = step.summary || {};
    return {
      input: summary.input
        ? escapeHtml(initialCapital(summary.input))
        : dependencyList(step) || "Nothing—this step starts a branch",
      output: summary.output
        ? escapeHtml(initialCapital(summary.output))
        : artifactList(step.outputs) || "",
      model: step.model
        ? "<code>" + escapeHtml(bare(step.model)) + "</code>"
        : "",
      effort: step.effort
        ? "<code>" + escapeHtml(bare(step.effort)) + "</code>"
        : "",
      calls: escapeHtml(step.calls_per_run),
    };
  }

  function stepDescription(step) {
    const summary = step.summary || {};
    return summary.description || step.spec_summary;
  }

  /* Everything the step note holds for one step, written into `body`: the
     description, then the record. The description is written by a language
     model from the step's source; that the report's prose is AI-written is
     said once, in the statement on AI use after the references, rather than
     under every step. */
  function stepDetail(body, step) {
    body.appendChild(el("p", { text: stepDescription(step) }));
    const record = stepRecord(step);
    const table = el("table", { class: "facts" });
    [
      factRow("Input", record.input),
      factRow("Output", record.output),
      factRow("Model", record.model),
      factRow("Reasoning effort", record.effort),
      factRow("Calls per run", record.calls),
    ].forEach((row) => {
      if (row) table.appendChild(row);
    });
    body.appendChild(table);
  }

  /* ----------------------------------------------------------- step note */

  /* The entry of the selected step, as a note anchored to its node. One note
     serves both charts, because two open at once would ask the reader which
     figure they are looking at; `owner` is the
     chart that raised it, and every other chart drops its selection so only
     one node on the page is ever highlighted.

     The note is placed above the node where there is room and below it
     otherwise, kept inside the viewport, and placed again on every scroll and
     resize while it is open, so it follows the node through the figure's own
     scroller and the page's. It is fixed to the viewport, so that it can be
     placed against the node wherever the page has scrolled to. */
  const tipState = { owner: null };

  function stepTip() {
    return document.getElementById("steptip");
  }

  function renderStepTip(step) {
    document.getElementById("steptip-title").textContent = step.label;
    const body = document.getElementById("steptip-body");
    clear(body);
    stepDetail(body, step);
  }

  function openStepTip(step, owner) {
    charts.forEach((chart) => {
      if (chart !== owner) chart.clearSelection();
    });
    tipState.owner = owner;
    renderStepTip(step);
    stepTip().hidden = false;
    placeStepTip();
  }

  function closeStepTip() {
    stepTip().hidden = true;
    tipState.owner = null;
    charts.forEach((chart) => {
      chart.clearSelection();
    });
  }

  function stepTipIsOpen() {
    return !stepTip().hidden;
  }

  /* The node the note belongs to, or null once the figure no longer draws it:
     a resize can replace the drawing it was pressed in. */
  function stepTipAnchor() {
    const host = tipState.owner && tipState.owner.host;
    if (!host || !host.isConnected) return null;
    return host.querySelector(".node.selected");
  }

  function placeStepTip() {
    const tip = stepTip();
    if (tip.hidden) return;
    const node = stepTipAnchor();
    if (!node) {
      closeStepTip();
      return;
    }
    const box = node.getBoundingClientRect();
    // A node scrolled out of the figure's own scroller is not on screen even
    // though its box has coordinates; the note waits until it comes back.
    const scroller = node.closest ? node.closest(".chart-scroll") : null;
    const frame = scroller
      ? scroller.getBoundingClientRect()
      : { left: 0, right: window.innerWidth };
    const onScreen = box.right > frame.left && box.left < frame.right;
    tip.style.visibility = onScreen ? "" : "hidden";
    if (!onScreen) return;

    const margin = 8;
    const gap = 10;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const width = tip.offsetWidth;
    const height = tip.offsetHeight;
    let left = box.left + box.width / 2 - width / 2;
    left = Math.max(margin, Math.min(left, viewportWidth - width - margin));
    let top = box.top - height - gap;
    let side = "above";
    if (top < margin) {
      top = box.bottom + gap;
      side = "below";
    }
    // Room on neither side: keep the note in view and let it cover the node
    // rather than run off the sheet.
    if (top + height > viewportHeight - margin) {
      top = Math.max(margin, viewportHeight - height - margin);
    }
    tip.style.left = left + "px";
    tip.style.top = top + "px";
    tip.setAttribute("data-side", side);
  }

  function bindStepTip() {
    document.getElementById("steptip-close").addEventListener("click", () => {
      closeStepTip();
    });
    window.addEventListener("resize", placeStepTip);
    // Capturing, so a scroll inside the figure's scroller, which does not
    // bubble, places the note as well as a scroll of the page.
    document.addEventListener("scroll", placeStepTip, true);
    // A press anywhere else closes the note. A node or a step reference is
    // left to its own handler, which selects or toggles; the note itself is
    // where the reader may be selecting text.
    document.addEventListener("click", (event) => {
      if (!stepTipIsOpen()) return;
      const inside = event.target.closest
        ? event.target.closest("#steptip, .node, .figref[data-step]")
        : null;
      if (inside) return;
      closeStepTip();
    });
  }

  /* ------------------------------------------------- shared computed parts */

  function stepsOf(laneId) {
    return DATA.steps.filter((step) => {
      return step.column === laneId;
    });
  }

  /* The factor a drawing is rendered at, in a column this wide.

     One function, so the size that gets chosen and the size that gets drawn can
     never be worked out differently: `sizeFor` asks it what each size would
     come to, and `refit` asks it what to write into the element. Taken from the
     largest pipeline, so every figure is drawn at one scale. */
  function fitScale(size, available) {
    const natural = widestPipeline(size);
    const budget = window.innerHeight * COMPACT_HEIGHT_BUDGET;
    return Math.min(
      available / natural.width,
      Math.max(budget / natural.height, COMPACT_MIN_SCALE),
      COMPACT_MAX_SCALE
    );
  }

  /* The room the widest pipeline's drawing needs at a size, in user units.

     Measured from the spec rather than written down, so adding a step that
     widens a layer moves the point at which the figures go compact, with
     nothing to remember to update. Measured once: it depends on the data, not
     on the window, so a resize never recomputes it. */
  const widestCache = {};
  function widestPipeline(size) {
    if (widestCache[size]) return widestCache[size];
    const largest = { width: 0, height: 0 };
    Object.keys(DATA.lanes).forEach((laneId) => {
      if (!stepsOf(laneId).length) return;
      const measured = createChart(null, laneId, 0, {
        measure: true,
        size: size,
      });
      largest.width = Math.max(largest.width, measured.width);
      largest.height = Math.max(largest.height, measured.height);
    });
    widestCache[size] = largest;
    return largest;
  }

  /* Anything that changes how much room a figure has: a resized window, a
     rotated phone, the contents rail appearing and taking its 214px column.
     Coalesced to one call a frame, since a drag fires this continuously. */
  const viewportListeners = [];
  let viewportPending = false;
  function onViewportChange(listener) {
    viewportListeners.push(listener);
  }
  window.addEventListener("resize", () => {
    if (viewportPending) return;
    viewportPending = true;
    window.requestAnimationFrame(() => {
      viewportPending = false;
      viewportListeners.forEach((listener) => {
        listener();
      });
    });
  });

  function factOf(key) {
    return (DATA.facts && DATA.facts[key]) || null;
  }

  /* A numbered caption. Figures are numbered in Python, in document order,
     so the number a component prints is the one the prose cites—a caption can
     never drift out of step with a cross-reference.

     A caption is one plain run of text: it says what the block is, adds only
     what the block cannot show for itself, and stops. Nothing inside it is
     set in a second register—there is no subtitle and no second size, and the
     number is bold only so the eye can find it from a cross-reference. It is
     written as sentences, so the terminating full stop is added here rather
     than trusted to every call site.

     Every caption is written before the block it names, because a reader
     scrolling down meets it first and needs to know what is coming. Print
     moves the figure captions back under their figures—see the caption rules
     in `style.css`—which is why the kind is on the element as a class.

     Every caption on the page is built here, as a `<figcaption>` inside its
     `<figure>`. */
  function figureCaption(kind, number, text) {
    return fillCaption(el("figcaption", {}), kind, number, text);
  }

  /* Rewritable, because a chart redraws its own caption on every draw. */
  function fillCaption(node, kind, number, text) {
    clear(node);
    node.className = "cap cap-" + kind.toLowerCase();
    node.appendChild(el("b", { text: kind + " " + number + "." }));
    node.appendChild(el("span", { text: " " + sentence(text) }));
    return node;
  }

  function sentence(text) {
    const trimmed = String(text).trim();
    return /[.!?]$/.test(trimmed) ? trimmed : trimmed + ".";
  }

  function code(text) {
    return el("code", { text: text });
  }

  function emptyNote(html) {
    return el("div", { class: "empty", html: html });
  }

  /* -------------------------------------------------------------- teaser */

  /* The teaser figure and the two-way link between it and the prose.

     The drawing is declared in `teaser.py` and only rendered here, so a part is
     a rectangle with an identity: `[[timeline|a chronology]]` in the Markdown
     compiles to a `.figref` carrying that id, and everything below is the
     relation between the two.

     The hard part is not the highlight, it is distance. A figure the reader has
     scrolled past cannot be lit usefully, and a figure scaled to a phone is not
     legible even when it is on screen. So a focus is resolved against what the
     reader can actually see, in one rule applied at every width:

       figure on screen and drawn large enough  ->  light the part where it is
       figure on screen but scaled down         ->  enlarge the part in place
       figure off screen                        ->  show the part beside the text

     There are no breakpoints in that rule. The scene is one coordinate system,
     a part is a sub-rectangle of it, and a viewBox is all three behaviors. */

  const TEASER = DATA.teaser || null;

  // Below this scale the scene's 9-unit type is under about 7px: the figure
  // still reads as a shape, but a part has to be enlarged to be read.
  const LEGIBLE_SCALE = 0.78;
  const PEEK_ASPECT = 16 / 9;
  const FOCUS_PAD = 16;
  const MIN_REGION = 232; // do not magnify a small part past legibility
  const HOVER_DELAY = 110;

  const teaserState = {
    view: null, // the mounted figure, once hydrated
    peek: null, // the docked detail panel, built on first use
    part: null,
    pinned: false,
    zoomed: false,
    mention: -1,
    hoverTimer: 0,
    animation: 0,
  };

  function teaserPart(partId) {
    if (!TEASER) return null;
    let found = null;
    TEASER.parts.forEach((part) => {
      if (part.id === partId) found = part;
    });
    return found;
  }

  function resolveMetric(text) {
    return String(text || "").replace(/\{([a-zA-Z0-9_.]+)\}/g, (match, key) => {
      const fact = factOf(key);
      return fact ? fact.display : "—";
    });
  }

  /* ------------------------------------------------------------ drawing */

  function sText(x, y, text, cls, anchor) {
    const node = svg("text", {
      x: x,
      y: y,
      class: cls || null,
      "text-anchor": anchor || null,
    });
    node.textContent = text;
    return node;
  }

  function sRect(x, y, w, h, cls) {
    return svg("rect", { x: x, y: y, width: w, height: h, class: cls || null });
  }

  function sPath(d, cls) {
    return svg("path", { d: d, class: cls || null });
  }

  /* A label that stays readable where it crosses a rule or a box edge, which in
     a figure this dense it always does—the channels between the columns are
     narrower than the words that describe what crosses them. Labels are
     collected and drawn last, above the parts, on their own paper. */
  function sLabel(labels, x, y, text, cls) {
    const width = text.length * 6 + 10;
    labels.appendChild(sRect(x - width / 2, y - 10, width, 14, "tlabel-bg"));
    labels.appendChild(sText(x, y, text, cls || "tedge-label", "middle"));
  }

  /* The tip sits exactly on (x, y): the parts are painted over the wires, so
     a head that reached past a box's edge would vanish under the box. */
  function arrowHead(host, x, y, direction) {
    const size = 5;
    const base =
      direction === "left" ? x + size : direction === "right" ? x - size : x;
    const points =
      direction === "down"
        ? [x, y + size, x - size + 1, y - 1, x + size - 1, y - 1]
        : [x, y, base, y - size + 1.5, base, y + size - 1.5];
    host.appendChild(
      sPath(
        "M" +
          points[0] +
          " " +
          points[1] +
          "L" +
          points[2] +
          " " +
          points[3] +
          "L" +
          points[4] +
          " " +
          points[5] +
          "Z",
        "tarrow"
      )
    );
  }

  function boxOf(partId) {
    const part = teaserPart(partId);
    return part ? { x: part.x, y: part.y, w: part.w, h: part.h } : null;
  }

  /* A wire and its label are one thing that connects a known set of parts, so
     both go in a group that names those parts. A focus reads that list to know
     whether the wire is part of what it is about; see `paintFocus`. */
  function wireGroup(host, ends) {
    const group = svg("g", { class: "twire", "data-ends": ends.join(" ") });
    host.appendChild(group);
    return group;
  }

  function drawLink(host, labels, link) {
    const from = boxOf(link.source);
    const to = boxOf(link.target);
    if (!from || !to) return;
    const ends = [link.source, link.target];
    const wire = wireGroup(host, ends);
    const cls = "tedge" + (link.kind === "call" ? " tedge-call" : "");
    const y1 = from.y + from.h * link.source_at;
    const y2 = to.y + to.h * link.target_at;
    const x1 = from.x + from.w;
    const x2 = to.x;
    const mid = x1 + (x2 - x1) * link.jog;
    wire.appendChild(
      sPath("M" + x1 + " " + y1 + "H" + mid + "V" + y2 + "H" + x2, cls)
    );
    arrowHead(wire, x2, y2, "right");
    if (link.both) arrowHead(wire, x1, y1, "left");
    if (link.label)
      sLabel(wireGroup(labels, ends), mid, Math.min(y1, y2) - 5, link.label);
  }

  /* Each routine fills one part's box. The vocabulary is closed: `teaser.py`
     may only name a decor that exists here, which is the same contract the
     component roster has with `report.py`. */
  const TEASER_DECOR = {
    plain: function () {},

    frame: function () {},

    sources: function (host, part) {
      part.lines.forEach((line, index) => {
        const y = part.y + 48 + index * 30;
        host.appendChild(sRect(part.x + 12, y, 15, 19, "tglyph"));
        host.appendChild(
          sPath(
            "M" + (part.x + 22) + " " + y + "v6h5", // the folded corner
            "tglyph-fold"
          )
        );
        host.appendChild(sText(part.x + 34, y + 13, line, "ttext"));
      });
    },

    /* What a box is configured with, listed under its name. The lines are
       settings rather than contents, so they are marked with a rule instead of
       the document glyph the source list carries. */
    traits: function (host, part) {
      part.lines.forEach((line, index) => {
        const y = part.y + 42 + index * 22;
        host.appendChild(sPath("M" + (part.x + 12) + " " + y + "h8", "trule"));
        host.appendChild(sText(part.x + 26, y + 4, line, "ttext"));
      });
    },

    /* One square per documented step, in the color of its kind: the size and
       the composition of a pipeline, without redrawing the pipeline. */
    steps: function (host, part) {
      const steps = DATA.steps.filter((step) => {
        return step.column === part.lane;
      });
      const size = 17;
      const gap = 4;
      const fits = Math.floor((part.w - 24 + gap) / (size + gap));
      // Balanced rows: a second row holding two squares reads as an accident.
      const perRow = Math.ceil(steps.length / Math.ceil(steps.length / fits));
      // The box is sized to match its counterpart in the interface column, so
      // the grid is centered in what the label leaves rather than pinned under
      // it—a single row of squares hanging from the title reads as unfinished.
      const rows = Math.ceil(steps.length / perRow);
      const top =
        part.y +
        40 +
        Math.max(0, (part.h - 52 - (rows * (size + gap) - gap)) / 2);
      steps.forEach((step, index) => {
        const row = Math.floor(index / perRow);
        const column = index % perRow;
        const cell = svg("g", { class: "tstep" });
        const rect = sRect(
          part.x + 12 + column * (size + gap),
          top + row * (size + gap),
          size,
          size,
          "tstep-box"
        );
        rect.setAttribute("fill", kindColor(step.kind));
        cell.appendChild(rect);
        const title = svg("title");
        title.textContent = step.label + "—" + DATA.kinds[step.kind].label;
        cell.appendChild(title);
        host.appendChild(cell);
      });
    },

    /* The four step kinds behind a label that says what the row classifies,
       laid out by the width each entry actually needs and wrapped when the box
       runs out—equal cells fit the shortest name and clipped the longest. */
    kinds: function (host, part) {
      let x = part.x;
      let y = part.y + 12;
      const heading = "Processing steps:";
      host.appendChild(sText(x, y + 10, heading, "ttext"));
      x += heading.length * 6.6 + 28;
      kindEntries().forEach((entry) => {
        const kind = entry[0];
        const width = DATA.kinds[kind].label.length * 7.2 + 44;
        if (x > part.x && x + width > part.x + part.w) {
          x = part.x;
          y += 19;
        }
        const swatch = sRect(x, y, 11, 11, "tswatch");
        swatch.setAttribute("fill", kindColor(kind));
        host.appendChild(swatch);
        host.appendChild(
          sText(x + 18, y + 10, DATA.kinds[kind].label, "ttext")
        );
        x += width;
      });
    },

    /* One thing the system produces, named by what it is and marked with the
       glyph the application draws for it—never by the file that stores it. */
    concept: function (host, part) {
      const mark = sceneGlyph(part.icon, part.x + 10, part.y + 11, 18);
      if (mark) host.appendChild(mark);
      host.appendChild(
        sText(part.x + 34, part.y + 24, part.label, "tconcept-name")
      );
    },

    /* A bounded sequence, drawn as a stack: the slide the reader is on, and the
       ones it snaps between. */
    slides: function (host, part) {
      const cardW = 112;
      const cardH = 92;
      const x = part.x + 16;
      const y = part.y + 46;
      host.appendChild(sRect(x + 14, y - 8, cardW, cardH, "tghost"));
      host.appendChild(sRect(x + 7, y - 4, cardW, cardH, "tghost"));
      host.appendChild(sRect(x, y, cardW, cardH, "tcard"));
      host.appendChild(
        svg("circle", { cx: x + 20, cy: y + 22, r: 11, class: "tportrait" })
      );
      host.appendChild(sRect(x + 38, y + 14, 58, 4, "tbar"));
      host.appendChild(sRect(x + 38, y + 24, 44, 4, "tbar"));
      host.appendChild(sRect(x + 12, y + 44, 88, 3, "tbar"));
      host.appendChild(sRect(x + 12, y + 52, 78, 3, "tbar"));
      // the persistent timeline along the foot of every slide
      host.appendChild(sPath("M" + (x + 12) + " " + (y + 74) + "h88", "trule"));
      [0, 18, 34, 55, 72, 88].forEach((offset, index) => {
        host.appendChild(
          svg("circle", {
            cx: x + 12 + offset,
            cy: y + 74,
            r: index === 2 ? 3 : 1.8,
            class: index === 2 ? "tdot on" : "tdot",
          })
        );
      });
    },

    /* A continuous document: one component held still while the cards that
       narrate it move over it. */
    sections: function (host, part) {
      const x = part.x + 16;
      const y = part.y + 44;
      host.appendChild(sRect(x, y, 118, 74, "tcard"));
      host.appendChild(sRect(x + 8, y + 8, 102, 34, "tpinned"));
      host.appendChild(sRect(x + 46, y + 16, 60, 16, "tnarration"));
      host.appendChild(sRect(x + 46, y + 44, 60, 16, "tnarration"));
      host.appendChild(sRect(x + 8, y + 50, 30, 3, "tbar"));
      host.appendChild(sRect(x + 8, y + 58, 22, 3, "tbar"));
      host.appendChild(
        sPath("M" + (x + 140) + " " + (y + 6) + "v56", "tedge-call")
      );
      arrowHead(host, x + 140, y + 66, "down");
    },
  };

  function drawPart(part) {
    const group = svg("g", {
      class: "tpart",
      "data-part": part.id,
      tabindex: "0",
      role: "button",
      "aria-label": part.label + ". " + part.blurb,
    });
    const title = svg("title");
    title.textContent = part.label;
    group.appendChild(title);
    if (part.frame !== "none") {
      group.appendChild(
        sRect(
          part.x,
          part.y,
          part.w,
          part.h,
          part.frame === "soft" ? "tframe soft" : "tframe"
        )
      );
    }
    if (part.decor !== "concept" && part.decor !== "kinds") {
      // A part that carries a concept wears its mark ahead of its name, so the
      // box that records the relationships and the box that draws them are
      // recognizably the same subject. The concept boxes lay themselves out the
      // same way, in their own decor, where the mark stands in for a title.
      const mark = sceneGlyph(part.icon, part.x + 11, part.y + 9, 14);
      if (mark) group.appendChild(mark);
      group.appendChild(
        sText(part.x + (mark ? 30 : 12), part.y + 20, part.label, "tpart-label")
      );
    }
    if (part.metric) {
      group.appendChild(
        sText(part.x + 12, part.y + 33, resolveMetric(part.metric), "tmetric")
      );
    }
    (TEASER_DECOR[part.decor] || TEASER_DECOR.plain)(group, part);
    // A transparent hit area last, so the whole box responds—including the
    // white space inside it. Children are appended after their parent, so a
    // nested part still wins the pointer.
    group.appendChild(sRect(part.x, part.y, part.w, part.h, "thit"));
    return group;
  }

  function buildTeaserSvg() {
    const root = svg("svg", {
      class: "teaser-svg",
      viewBox: "0 0 " + TEASER.width + " " + TEASER.height,
      preserveAspectRatio: "xMidYMid meet",
      role: "img",
      "aria-label":
        "The system end to end: sources and language-model inference, two " +
        "generation pipelines, the data they write, the interface that reads " +
        "it, and along the foot the four kinds of step the pipelines are made of.",
    });
    root.style.aspectRatio = TEASER.width + " / " + TEASER.height;

    const chrome = svg("g", { class: "tchrome" });
    TEASER.stages.forEach((stage) => {
      const y = stage.y || 20;
      chrome.appendChild(sText(stage.x, y, stage.label, "tstage"));
      chrome.appendChild(
        sPath("M" + stage.x + " " + (y + 7) + "h" + stage.w, "tstage-rule")
      );
    });
    root.appendChild(chrome);

    // Three layers: wires under the parts they connect, and the wires' labels
    // over both, since a channel between two columns is narrower than the word
    // for what crosses it.
    const wires = svg("g", { class: "twires" });
    const labels = svg("g", { class: "tlabels" });
    TEASER.links.forEach((link) => {
      drawLink(wires, labels, link);
    });
    root.appendChild(wires);

    const parts = svg("g", { class: "tparts" });
    TEASER.parts.forEach((part) => {
      parts.appendChild(drawPart(part));
    });
    root.appendChild(parts);
    root.appendChild(labels);
    return root;
  }

  /* --------------------------------------------------------- focus regions */

  function ancestorsOf(partId) {
    const chain = [];
    let current = teaserPart(partId);
    while (current && current.parent) {
      chain.push(current.parent);
      current = teaserPart(current.parent);
    }
    return chain;
  }

  function childrenOf(partId) {
    return TEASER.parts
      .filter((part) => {
        return part.parent === partId;
      })
      .map((part) => {
        return part.id;
      });
  }

  /* The rectangle to show when a part is the subject: the part, some of what
     surrounds it, and the aspect of whatever is going to display it—grown, never
     cropped, so a focus never distorts or hides part of its subject. */
  function focusRegion(partId, aspect) {
    const part = teaserPart(partId);
    if (!part) return [0, 0, TEASER.width, TEASER.height];
    let width = Math.max(part.w + FOCUS_PAD * 2, MIN_REGION);
    let height = Math.max(part.h + FOCUS_PAD * 2, MIN_REGION / aspect);
    if (width / height < aspect) width = height * aspect;
    else height = width / aspect;
    width = Math.min(width, TEASER.width);
    height = Math.min(height, TEASER.height);
    let x = part.x + part.w / 2 - width / 2;
    let y = part.y + part.h / 2 - height / 2;
    x = Math.max(0, Math.min(x, TEASER.width - width));
    y = Math.max(0, Math.min(y, TEASER.height - height));
    return [x, y, width, height];
  }

  function readViewBox(node) {
    return node
      .getAttribute("viewBox")
      .split(/[\s,]+/)
      .map(Number);
  }

  function writeViewBox(node, box) {
    node.setAttribute(
      "viewBox",
      box
        .map((value) => {
          return Math.round(value * 100) / 100;
        })
        .join(" ")
    );
  }

  function reducedMotion() {
    return (
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  function animateViewBox(node, target) {
    if (teaserState.animation) {
      window.cancelAnimationFrame(teaserState.animation);
      teaserState.animation = 0;
    }
    const from = readViewBox(node);
    if (reducedMotion()) {
      writeViewBox(node, target);
      return;
    }
    const start = window.performance ? window.performance.now() : Date.now();
    const duration = 240;
    function frame(now) {
      const t = Math.min(1, (now - start) / duration);
      const eased = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
      writeViewBox(
        node,
        from.map((value, index) => {
          return value + (target[index] - value) * eased;
        })
      );
      if (t < 1) teaserState.animation = window.requestAnimationFrame(frame);
      else teaserState.animation = 0;
    }
    teaserState.animation = window.requestAnimationFrame(frame);
  }

  /* --------------------------------------------------------- highlighting */

  function paintFocus(root, partId) {
    const related = {};
    if (partId) {
      related[partId] = "on";
      ancestorsOf(partId).forEach((id) => {
        related[id] = "kin";
      });
      childrenOf(partId).forEach((id) => {
        related[id] = "kin";
      });
    }
    root.classList.toggle("has-focus", !!partId);
    Array.prototype.forEach.call(root.querySelectorAll(".tpart"), (node) => {
      const state = related[node.getAttribute("data-part")];
      node.classList.toggle("is-on", state === "on");
      node.classList.toggle("is-kin", state === "kin");
      node.classList.toggle("is-off", !!partId && !state);
    });
    // A wire recedes with the parts it joins: it stays lit while either end is
    // still in the picture, so a focus shows what the part is connected to and
    // nothing else. Without this the traffic between the dimmed boxes keeps its
    // full contrast and reads as the loudest thing on the figure.
    Array.prototype.forEach.call(root.querySelectorAll(".twire"), (node) => {
      const ends = (node.getAttribute("data-ends") || "").split(" ");
      const joined = ends.some((id) => {
        return !!related[id];
      });
      node.classList.toggle("is-off", !!partId && !joined);
    });
  }

  function mentionsOf(partId) {
    if (!partId) return [];
    return Array.prototype.slice.call(
      document.querySelectorAll('.figref[data-part="' + partId + '"]')
    );
  }

  function markRefs(partId) {
    Array.prototype.forEach.call(
      document.querySelectorAll(".figref:not([data-shot]):not([data-step])"),
      (node) => {
        const lit = !!partId && node.getAttribute("data-part") === partId;
        node.classList.toggle("is-lit", lit);
        node.setAttribute(
          "aria-expanded",
          lit && teaserState.pinned ? "true" : "false"
        );
      }
    );
  }

  /* --------------------------------------------------------- the detail panel */

  function ensurePeek() {
    if (teaserState.peek) return teaserState.peek;
    const clone = teaserState.view.svg.cloneNode(true);
    clone.setAttribute("aria-hidden", "true");
    clone.removeAttribute("role");
    clone.removeAttribute("aria-label");
    clone.style.aspectRatio = "16 / 9";
    Array.prototype.forEach.call(clone.querySelectorAll(".tpart"), (node) => {
      node.removeAttribute("tabindex");
      node.removeAttribute("role");
    });

    const title = el("span", { class: "figpeek-title" });
    const jump = el("button", {
      class: "figpeek-act",
      type: "button",
      text: "Show in figure",
      onclick: function () {
        scrollToFigure();
      },
    });
    const close = el("button", {
      class: "figpeek-close",
      type: "button",
      "aria-label": "Close the figure detail",
      html: "&times;",
      onclick: function () {
        clearTeaserFocus();
      },
    });
    const blurb = el("p", { class: "figpeek-blurb" });
    const panel = el(
      "aside",
      {
        class: "figpeek",
        id: "figpeek",
        "aria-label": "Detail of the teaser figure",
        hidden: "hidden",
      },
      [
        el("div", { class: "figpeek-head" }, [
          el("span", {
            class: "figpeek-kicker",
            text: teaserState.view.figureLabel,
          }),
          title,
          jump,
          close,
        ]),
        el("div", { class: "figpeek-view" }, [clone]),
        blurb,
      ]
    );
    document.body.appendChild(panel);
    teaserState.peek = {
      panel: panel,
      svg: clone,
      title: title,
      blurb: blurb,
    };
    return teaserState.peek;
  }

  function openPeek(partId, keepRefVisible) {
    const peek = ensurePeek();
    const part = teaserPart(partId);
    peek.title.textContent = part.label;
    peek.blurb.textContent = part.blurb;
    paintFocus(peek.svg, partId);
    const wasHidden = peek.panel.hasAttribute("hidden");
    peek.panel.removeAttribute("hidden");
    const region = focusRegion(partId, PEEK_ASPECT);
    if (wasHidden) writeViewBox(peek.svg, region);
    else animateViewBox(peek.svg, region);
    if (keepRefVisible) keepMentionClear(peek.panel);
  }

  function closePeek() {
    if (teaserState.peek)
      teaserState.peek.panel.setAttribute("hidden", "hidden");
  }

  /* On a phone the panel is a sheet along the bottom edge, so the phrase the
     reader just touched can end up behind it. Move the page, not the panel:
     the point of the panel is to be read together with that sentence. */
  function keepMentionClear(panel) {
    const active = document.activeElement;
    const ref =
      active && active.classList && active.classList.contains("figref")
        ? active
        : mentionsOf(teaserState.part)[0];
    if (!ref) return;
    window.requestAnimationFrame(() => {
      const panelBox = panel.getBoundingClientRect();
      const refBox = ref.getBoundingClientRect();
      const overlap = refBox.bottom - panelBox.top + 20;
      if (panelBox.top > window.innerHeight - 8 || overlap <= 0) return;
      window.scrollBy({
        top: overlap,
        behavior: reducedMotion() ? "auto" : "smooth",
      });
    });
  }

  /* ------------------------------------------------------------ placement */

  function figureVisibility() {
    const box = teaserState.view.figure.getBoundingClientRect();
    const visible =
      Math.min(box.bottom, window.innerHeight) - Math.max(box.top, 0);
    return box.height ? Math.max(0, visible) / box.height : 0;
  }

  function figureScale() {
    const box = teaserState.view.svg.getBoundingClientRect();
    return box.width / TEASER.width;
  }

  function scrollToFigure() {
    teaserState.view.figure.scrollIntoView({
      block: "center",
      behavior: reducedMotion() ? "auto" : "smooth",
    });
    closePeek();
  }

  function resetZoom() {
    if (!teaserState.zoomed) return;
    teaserState.zoomed = false;
    animateViewBox(teaserState.view.svg, [0, 0, TEASER.width, TEASER.height]);
  }

  function zoomToPart(partId) {
    teaserState.zoomed = true;
    animateViewBox(
      teaserState.view.svg,
      focusRegion(partId, TEASER.width / TEASER.height)
    );
  }

  /* The one rule. Where the reader is decides which of the three behaviors a
     focus gets—never a media query, which cannot see the scroll position. */
  function placeFocus(fromRef) {
    if (!teaserState.part) {
      closePeek();
      resetZoom();
      return;
    }
    if (figureVisibility() > 0.55) {
      closePeek();
      if (figureScale() < LEGIBLE_SCALE) zoomToPart(teaserState.part);
      else resetZoom();
      return;
    }
    resetZoom();
    openPeek(teaserState.part, fromRef);
  }

  function setTeaserFocus(partId, options) {
    if (!teaserState.view || !teaserPart(partId)) return;
    // One focus at a time across the linked figures: taking the teaser's
    // releases any screenshot part, and vice versa.
    clearShotFocus();
    const opts = options || {};
    teaserState.part = partId;
    teaserState.pinned = !!opts.pinned;
    teaserState.mention = -1;
    paintFocus(teaserState.view.svg, partId);
    markRefs(partId);
    placeFocus(opts.fromRef);
    renderTeaserStatus();
  }

  function clearTeaserFocus() {
    if (!teaserState.view || !teaserState.part) return;
    teaserState.part = null;
    teaserState.pinned = false;
    paintFocus(teaserState.view.svg, null);
    markRefs(null);
    closePeek();
    resetZoom();
    renderTeaserStatus();
  }

  /* ------------------------------------------------ the figure's status line */

  function showMention(step) {
    const mentions = mentionsOf(teaserState.part);
    if (!mentions.length) return;
    teaserState.mention =
      (teaserState.mention + step + mentions.length) % mentions.length;
    const target = mentions[teaserState.mention];
    target.scrollIntoView({
      block: "center",
      behavior: reducedMotion() ? "auto" : "smooth",
    });
    target.classList.add("is-found");
    window.setTimeout(() => {
      target.classList.remove("is-found");
    }, 1400);
    renderTeaserStatus();
  }

  function renderTeaserStatus(overrideId) {
    const host = teaserState.view.status;
    clear(host);
    const part = teaserPart(overrideId || teaserState.part);
    if (!part) {
      host.appendChild(
        el("p", { class: "teaser-text teaser-hint" }, [
          el("span", {
            text:
              "Select a part for what it is and where the text discusses it. " +
              "Marked phrases in the text point back.",
          }),
        ])
      );
      return;
    }

    host.appendChild(
      el("p", { class: "teaser-text" }, [
        el("b", { text: part.label + ". " }),
        el("span", { text: part.blurb }),
      ])
    );

    const controls = el("span", { class: "teaser-controls" });
    const mentions = mentionsOf(part.id);
    if (mentions.length) {
      controls.appendChild(
        el("button", {
          class: "teaser-act",
          type: "button",
          "aria-label": "Previous mention in the text",
          text: "‹",
          onclick: function () {
            showMention(-1);
          },
        })
      );
      controls.appendChild(
        el("span", {
          class: "teaser-count",
          text:
            (teaserState.mention < 0
              ? mentions.length
              : teaserState.mention + 1) +
            (teaserState.mention < 0
              ? mentions.length === 1
                ? " mention"
                : " mentions"
              : " of " + mentions.length),
        })
      );
      controls.appendChild(
        el("button", {
          class: "teaser-act",
          type: "button",
          "aria-label": "Next mention in the text",
          text: "›",
          onclick: function () {
            showMention(1);
          },
        })
      );
    }
    if (teaserState.zoomed) {
      controls.appendChild(
        el("button", {
          class: "teaser-act",
          type: "button",
          text: "Whole figure",
          onclick: function () {
            clearTeaserFocus();
          },
        })
      );
    }
    controls.appendChild(
      el("button", {
        class: "teaser-act",
        type: "button",
        text: "Clear",
        onclick: function () {
          clearTeaserFocus();
        },
      })
    );
    host.appendChild(controls);
  }

  /* The status line has to be able to change without moving the page.

     It sits above a document the reader is pointing at: if it grew from a hint
     to a sentence, everything below it shifted, the phrase under the cursor
     moved out from under the cursor, and the focus it had just opened dropped
     again—a flicker loop, and the exact opposite of bringing the two closer
     together. So the strip reserves the height of its tallest state up front,
     measured at the current width rather than guessed. */
  function reserveStatusHeight() {
    const host = teaserState.view.status;
    host.style.minHeight = "";
    // Only a pointer that hovers can be shaken off by a reflow. Where the
    // reader has to tap, the strip grows and shrinks with its content rather
    // than holding empty space open under a small figure.
    if (!hoverCapable()) {
      renderTeaserStatus();
      return;
    }
    let longest = TEASER.parts[0];
    TEASER.parts.forEach((part) => {
      if (
        part.label.length + part.blurb.length >
        longest.label.length + longest.blurb.length
      ) {
        longest = part;
      }
    });
    renderTeaserStatus(longest.id);
    const height = host.getBoundingClientRect().height;
    host.style.minHeight = Math.ceil(height) + "px";
    renderTeaserStatus();
  }

  /* ------------------------------------------------------------------ wiring */

  function hoverCapable() {
    return !window.matchMedia || window.matchMedia("(hover: hover)").matches;
  }

  function bindTeaserRefs() {
    const canHover = hoverCapable();

    // A `.figref` carrying `data-shot` points into a screenshot figure and is
    // handled by `bindShotRefs`; only the bare ones are the teaser's.
    function teaserRef(target) {
      const ref = target.closest ? target.closest(".figref") : null;
      if (!ref) return null;
      if (ref.hasAttribute("data-shot") || ref.hasAttribute("data-step"))
        return null;
      return ref;
    }

    document.addEventListener("click", (event) => {
      const ref = teaserRef(event.target);
      if (!ref) return;
      event.preventDefault();
      const partId = ref.getAttribute("data-part");
      if (teaserState.pinned && teaserState.part === partId) clearTeaserFocus();
      else setTeaserFocus(partId, { pinned: true, fromRef: true });
    });

    document.addEventListener("focusin", (event) => {
      const ref = teaserRef(event.target);
      if (!ref || teaserState.pinned) return;
      setTeaserFocus(ref.getAttribute("data-part"), { fromRef: true });
    });

    if (!canHover) return;

    document.addEventListener("mouseover", (event) => {
      const ref = teaserRef(event.target);
      if (!ref || teaserState.pinned) return;
      window.clearTimeout(teaserState.hoverTimer);
      teaserState.hoverTimer = window.setTimeout(() => {
        setTeaserFocus(ref.getAttribute("data-part"), { fromRef: true });
      }, HOVER_DELAY);
    });

    document.addEventListener("mouseout", (event) => {
      const ref = teaserRef(event.target);
      if (!ref || teaserState.pinned) return;
      window.clearTimeout(teaserState.hoverTimer);
      clearTeaserFocus();
    });
  }

  function bindTeaserParts(root) {
    Array.prototype.forEach.call(root.querySelectorAll(".tpart"), (node) => {
      const partId = node.getAttribute("data-part");
      node.addEventListener("click", (event) => {
        event.stopPropagation();
        if (teaserState.pinned && teaserState.part === partId)
          clearTeaserFocus();
        else setTeaserFocus(partId, { pinned: true });
      });
      node.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        setTeaserFocus(partId, { pinned: true });
      });
      if (!hoverCapable()) return;
      node.addEventListener("mouseenter", () => {
        if (teaserState.pinned) return;
        setTeaserFocus(partId, {});
      });
      node.addEventListener("mouseleave", () => {
        if (teaserState.pinned) return;
        clearTeaserFocus();
      });
    });
  }

  function createTeaser(host, figureNumber) {
    if (!TEASER || !TEASER.parts.length) {
      host.appendChild(
        emptyNote("The teaser figure is missing from the build payload.")
      );
      return;
    }
    const root = buildTeaserSvg();
    // A div, not a paragraph: the report's own paragraph typography applies to
    // everything inside `.report`, and this strip is chrome.
    const status = el("div", { class: "teaser-status", "aria-live": "polite" });
    // The caption comes first, as it does in every other figure on this page,
    // and the status strip stays under the drawing: it reports what is on
    // screen, so it belongs with the drawing rather than with the caption.
    const figure = el("figure", { class: "figure teaser", id: "fig-teaser" }, [
      figureCaption("Figure", figureNumber, TEASER.caption),
      el("div", { class: "teaser-frame" }, [root]),
      status,
    ]);
    host.appendChild(figure);

    teaserState.view = {
      svg: root,
      figure: figure,
      status: status,
      figureLabel: "Figure " + figureNumber,
    };

    bindTeaserParts(root);
    bindTeaserRefs();
    renderTeaserStatus();

    reserveStatusHeight();

    // A focus is placed against what is on screen, so scrolling and resizing
    // can change which of the three behaviors is right while it is held.
    let pending = 0;
    function reflow(remeasure) {
      pending = 0;
      if (remeasure) reserveStatusHeight();
      if (teaserState.part) placeFocus(false);
    }
    window.addEventListener(
      "scroll",
      () => {
        if (!pending && teaserState.pinned) {
          pending = window.requestAnimationFrame(() => {
            reflow(false);
          });
        }
      },
      { passive: true }
    );
    window.addEventListener("resize", () => {
      if (pending) window.cancelAnimationFrame(pending);
      pending = window.requestAnimationFrame(() => {
        reflow(true);
      });
    });
  }

  /* ---------------------------------------------- screenshot part linking */

  /* A screenshot with declared parts gets the same two-way relation the
     teaser has: `[[landing.carousel|a carousel]]` in the Markdown compiles to
     a `.figref` carrying the shot and the part, and a part is a rectangle of
     the capture, in the CSS pixels it was declared in.

     The one rule is the teaser's rule, resolved against what the reader can
     see:

       figure on screen and the part legible  ->  light the part where it is
       figure on screen but the part small    ->  enlarge the part in place
       figure off screen                      ->  show the part beside the text

     A drawing enlarges by viewBox; a photograph enlarges by transforming the
     picture and its overlay together inside a clipping box, which changes
     what the box shows and never the room the figure takes. Enlargement stops
     at the capture's own pixel density—a part blown up past the pixels that
     were taken for it is bigger, not more legible. */

  const SHOT_FOCUS_PAD = 12; // CSS pixels of context kept around a focused part
  const SHOT_LEGIBLE_PX = 240; // a part displayed narrower than this is enlarged

  const shotViews = {}; // shot id -> the mounted figure, once hydrated

  const shotState = {
    shot: null,
    part: null,
    pinned: false,
    mention: -1,
    hoverTimer: 0,
    peek: null,
    bound: false,
  };

  function activeShotView() {
    return shotState.shot ? shotViews[shotState.shot] || null : null;
  }

  function shotPartOf(view, partId) {
    let found = null;
    view.shot.parts.forEach((part) => {
      if (part.id === partId) found = part;
    });
    return found;
  }

  /* The rectangle to show for a part: the part, some context, and the aspect
     of whatever displays it—grown, never cropped, exactly as `focusRegion`
     grows a teaser part. `minWidth` is the density cap, already resolved to
     image pixels by the caller. */
  function shotFocusRegion(view, partId, aspect, minWidth) {
    const sceneW = view.shot.width;
    const sceneH = view.shot.height;
    const part = shotPartOf(view, partId);
    if (!part) return [0, 0, sceneW, sceneH];
    let width = Math.max(part.w + SHOT_FOCUS_PAD * 2, minWidth || 0);
    let height = part.h + SHOT_FOCUS_PAD * 2;
    if (width / height < aspect) width = height * aspect;
    else height = width / aspect;
    width = Math.min(width, sceneW);
    height = Math.min(height, sceneH);
    let x = part.x + part.w / 2 - width / 2;
    let y = part.y + part.h / 2 - height / 2;
    x = Math.max(0, Math.min(x, sceneW - width));
    y = Math.max(0, Math.min(y, sceneH - height));
    return [x, y, width, height];
  }

  function paintShotFocus(view, partId) {
    const part = partId ? shotPartOf(view, partId) : null;
    view.svg.classList.toggle("has-focus", !!part);
    Array.prototype.forEach.call(
      view.svg.querySelectorAll(".spart"),
      (node) => {
        node.classList.toggle(
          "is-on",
          !!part && node.getAttribute("data-part") === partId
        );
      }
    );
    // One even-odd path dims everything but the subject, so the region reads
    // as a hole in the shade rather than a box drawn over the picture.
    view.scrim.setAttribute(
      "d",
      part
        ? "M0 0H" +
            view.shot.width +
            "V" +
            view.shot.height +
            "H0Z" +
            "M" +
            part.x +
            " " +
            part.y +
            "H" +
            (part.x + part.w) +
            "V" +
            (part.y + part.h) +
            "H" +
            part.x +
            "Z"
        : ""
    );
  }

  function shotRefsOf(shotId, partId) {
    if (!shotId || !partId) return [];
    return Array.prototype.slice.call(
      document.querySelectorAll(
        '.figref[data-shot="' + shotId + '"][data-part="' + partId + '"]'
      )
    );
  }

  function markShotRefs(shotId, partId) {
    Array.prototype.forEach.call(
      document.querySelectorAll(".figref[data-shot]"),
      (node) => {
        const lit =
          !!partId &&
          node.getAttribute("data-shot") === shotId &&
          node.getAttribute("data-part") === partId;
        node.classList.toggle("is-lit", lit);
        node.setAttribute(
          "aria-expanded",
          lit && shotState.pinned ? "true" : "false"
        );
      }
    );
  }

  function applyShotZoom(view, region) {
    if (!region) {
      view.zoomed = false;
      view.canvas.style.transform = "";
      return;
    }
    view.zoomed = true;
    const scale = view.shot.width / region[2];
    view.canvas.style.transform =
      "scale(" +
      scale +
      ") translate(" +
      (-region[0] / view.shot.width) * 100 +
      "%, " +
      (-region[1] / view.shot.height) * 100 +
      "%)";
  }

  function shotVisibility(view) {
    const box = view.figure.getBoundingClientRect();
    const visible =
      Math.min(box.bottom, window.innerHeight) - Math.max(box.top, 0);
    const shown = box.height ? Math.max(0, visible) / box.height : 0;
    // A margin figure the next one has slid over is on screen only by its
    // rectangle; what the reader sees of it is what is left after the fade.
    return shown * marginFadeOf(view.figure);
  }

  /* ------------------------------------------- the screenshot detail panel */

  function ensureShotPeek() {
    if (shotState.peek) return shotState.peek;
    const kicker = el("span", { class: "figpeek-kicker" });
    const title = el("span", { class: "figpeek-title" });
    const jump = el("button", {
      class: "figpeek-act",
      type: "button",
      text: "Show in figure",
      onclick: function () {
        const view = activeShotView();
        if (view && !revealMarginFigure(view.figure)) {
          view.figure.scrollIntoView({
            block: "center",
            behavior: reducedMotion() ? "auto" : "smooth",
          });
        }
        closeShotPeek();
      },
    });
    const close = el("button", {
      class: "figpeek-close",
      type: "button",
      "aria-label": "Close the figure detail",
      html: "&times;",
      onclick: function () {
        clearShotFocus();
      },
    });
    const img = el("img", { class: "figpeek-shot", alt: "" });
    const mark = el("span", { class: "figpeek-mark" });
    const blurb = el("p", { class: "figpeek-blurb" });
    const panel = el(
      "aside",
      {
        class: "figpeek",
        "aria-label": "Detail of a screenshot figure",
        hidden: "hidden",
      },
      [
        el("div", { class: "figpeek-head" }, [kicker, title, jump, close]),
        el("div", { class: "figpeek-view" }, [
          el("div", { class: "figpeek-stage" }, [img, mark]),
        ]),
        blurb,
      ]
    );
    document.body.appendChild(panel);
    shotState.peek = {
      panel: panel,
      kicker: kicker,
      title: title,
      blurb: blurb,
      img: img,
      mark: mark,
    };
    return shotState.peek;
  }

  /* The crop is done by positioning: the picture is set into the panel at the
     size that fills it with the focus region, all in percentages of the
     region, so nothing has to be measured. */
  function openShotPeek(view, partId, keepRefVisible) {
    const peek = ensureShotPeek();
    const part = shotPartOf(view, partId);
    peek.kicker.textContent = view.figureLabel;
    peek.title.textContent = part.label;
    peek.blurb.textContent = part.blurb;
    const region = shotFocusRegion(
      view,
      partId,
      PEEK_ASPECT,
      MIN_REGION / (view.shot.scale || 1)
    );
    peek.img.src = view.shot.src;
    peek.img.style.width = (view.shot.width / region[2]) * 100 + "%";
    peek.img.style.left = (-region[0] / region[2]) * 100 + "%";
    peek.img.style.top = (-region[1] / region[3]) * 100 + "%";
    peek.mark.style.left = ((part.x - region[0]) / region[2]) * 100 + "%";
    peek.mark.style.top = ((part.y - region[1]) / region[3]) * 100 + "%";
    peek.mark.style.width = (part.w / region[2]) * 100 + "%";
    peek.mark.style.height = (part.h / region[3]) * 100 + "%";
    peek.panel.removeAttribute("hidden");
    if (keepRefVisible) keepShotMentionClear(peek.panel);
  }

  function closeShotPeek() {
    if (shotState.peek) shotState.peek.panel.setAttribute("hidden", "hidden");
  }

  // The same courtesy `keepMentionClear` pays: on a phone the panel is a
  // sheet, and the phrase the reader just touched must not end up behind it.
  function keepShotMentionClear(panel) {
    const active = document.activeElement;
    const ref =
      active &&
      active.classList &&
      active.classList.contains("figref") &&
      active.hasAttribute("data-shot")
        ? active
        : shotRefsOf(shotState.shot, shotState.part)[0];
    if (!ref) return;
    window.requestAnimationFrame(() => {
      const panelBox = panel.getBoundingClientRect();
      const refBox = ref.getBoundingClientRect();
      const overlap = refBox.bottom - panelBox.top + 20;
      if (panelBox.top > window.innerHeight - 8 || overlap <= 0) return;
      window.scrollBy({
        top: overlap,
        behavior: reducedMotion() ? "auto" : "smooth",
      });
    });
  }

  /* ------------------------------------------------ placing a shot focus */

  function placeShotFocus(fromRef) {
    const view = activeShotView();
    if (!view || !shotState.part) {
      closeShotPeek();
      return;
    }
    if (shotVisibility(view) > 0.55) {
      closeShotPeek();
      const displayed = view.clip.getBoundingClientRect().width;
      const part = shotPartOf(view, shotState.part);
      const shown = (part.w * displayed) / view.shot.width;
      if (shown < SHOT_LEGIBLE_PX) {
        applyShotZoom(
          view,
          shotFocusRegion(
            view,
            shotState.part,
            view.shot.width / view.shot.height,
            displayed / (view.shot.scale || 1)
          )
        );
      } else {
        applyShotZoom(view, null);
      }
      return;
    }
    applyShotZoom(view, null);
    openShotPeek(view, shotState.part, fromRef);
  }

  function setShotFocus(shotId, partId, options) {
    const view = shotViews[shotId];
    if (!view || !shotPartOf(view, partId)) return;
    clearTeaserFocus();
    if (shotState.shot && shotState.shot !== shotId) clearShotFocus();
    const opts = options || {};
    shotState.shot = shotId;
    shotState.part = partId;
    shotState.pinned = !!opts.pinned;
    shotState.mention = -1;
    paintShotFocus(view, partId);
    markShotRefs(shotId, partId);
    placeShotFocus(opts.fromRef);
    renderShotStatus(view);
  }

  function clearShotFocus() {
    const view = activeShotView();
    shotState.part = null;
    shotState.pinned = false;
    shotState.mention = -1;
    shotState.shot = null;
    if (!view) return;
    paintShotFocus(view, null);
    markShotRefs(view.shot.id, null);
    closeShotPeek();
    applyShotZoom(view, null);
    renderShotStatus(view);
  }

  /* --------------------------------------------- the shot's status line */

  function showShotMention(view, step) {
    const mentions = shotRefsOf(shotState.shot, shotState.part);
    if (!mentions.length) return;
    shotState.mention =
      (shotState.mention + step + mentions.length) % mentions.length;
    const target = mentions[shotState.mention];
    target.scrollIntoView({
      block: "center",
      behavior: reducedMotion() ? "auto" : "smooth",
    });
    target.classList.add("is-found");
    window.setTimeout(() => {
      target.classList.remove("is-found");
    }, 1400);
    renderShotStatus(view);
  }

  // The same strip the teaser wears, under the same rules; only the sources
  // differ, so the stylesheet is shared through the same class names.
  function renderShotStatus(view, overrideId) {
    const host = view.status;
    clear(host);
    const focused = shotState.shot === view.shot.id ? shotState.part : null;
    const part = shotPartOf(view, overrideId || focused || "");
    if (!part) {
      host.appendChild(
        el("p", { class: "teaser-text teaser-hint" }, [
          el("span", {
            text:
              "Select a marked region for what it is and where the text " +
              "discusses it. Marked phrases in the text point back.",
          }),
        ])
      );
      return;
    }

    host.appendChild(
      el("p", { class: "teaser-text" }, [
        el("b", { text: part.label + ". " }),
        el("span", { text: part.blurb }),
      ])
    );

    const controls = el("span", { class: "teaser-controls" });
    const mentions = shotRefsOf(view.shot.id, part.id);
    if (mentions.length) {
      controls.appendChild(
        el("button", {
          class: "teaser-act",
          type: "button",
          "aria-label": "Previous mention in the text",
          text: "‹",
          onclick: function () {
            showShotMention(view, -1);
          },
        })
      );
      controls.appendChild(
        el("span", {
          class: "teaser-count",
          text:
            (shotState.mention < 0 ? mentions.length : shotState.mention + 1) +
            (shotState.mention < 0
              ? mentions.length === 1
                ? " mention"
                : " mentions"
              : " of " + mentions.length),
        })
      );
      controls.appendChild(
        el("button", {
          class: "teaser-act",
          type: "button",
          "aria-label": "Next mention in the text",
          text: "›",
          onclick: function () {
            showShotMention(view, 1);
          },
        })
      );
    }
    if (view.zoomed) {
      controls.appendChild(
        el("button", {
          class: "teaser-act",
          type: "button",
          text: "Whole figure",
          onclick: function () {
            clearShotFocus();
          },
        })
      );
    }
    controls.appendChild(
      el("button", {
        class: "teaser-act",
        type: "button",
        text: "Clear",
        onclick: function () {
          clearShotFocus();
        },
      })
    );
    host.appendChild(controls);
  }

  function reserveShotStatusHeight(view) {
    const host = view.status;
    host.style.minHeight = "";
    if (!hoverCapable()) {
      renderShotStatus(view);
      return;
    }
    let longest = view.shot.parts[0];
    view.shot.parts.forEach((part) => {
      if (
        part.label.length + part.blurb.length >
        longest.label.length + longest.blurb.length
      ) {
        longest = part;
      }
    });
    renderShotStatus(view, longest.id);
    const height = host.getBoundingClientRect().height;
    host.style.minHeight = Math.ceil(height) + "px";
    renderShotStatus(view);
  }

  /* --------------------------------------------------- wiring the shots */

  function buildShotOverlay(shot) {
    const root = svg("svg", {
      class: "shot-parts",
      viewBox: "0 0 " + shot.width + " " + shot.height,
      // The picture is the geometry; the overlay covers it exactly.
      preserveAspectRatio: "none",
    });
    const scrim = svg("path", {
      class: "spart-scrim",
      "fill-rule": "evenodd",
      d: "",
    });
    root.appendChild(scrim);
    shot.parts.forEach((part) => {
      const group = svg("g", {
        class: "spart",
        "data-part": part.id,
        tabindex: "0",
        role: "button",
        "aria-label": part.label + ". " + part.blurb,
      });
      const title = svg("title");
      title.textContent = part.label;
      group.appendChild(title);
      group.appendChild(
        svg("rect", {
          x: part.x,
          y: part.y,
          width: part.w,
          height: part.h,
          class: "spart-box",
        })
      );
      root.appendChild(group);
    });
    return { root: root, scrim: scrim };
  }

  function bindShotParts(view) {
    Array.prototype.forEach.call(
      view.svg.querySelectorAll(".spart"),
      (node) => {
        const partId = node.getAttribute("data-part");
        node.addEventListener("click", (event) => {
          event.stopPropagation();
          if (
            shotState.pinned &&
            shotState.shot === view.shot.id &&
            shotState.part === partId
          )
            clearShotFocus();
          else setShotFocus(view.shot.id, partId, { pinned: true });
        });
        node.addEventListener("keydown", (event) => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          setShotFocus(view.shot.id, partId, { pinned: true });
        });
        if (!hoverCapable()) return;
        node.addEventListener("mouseenter", () => {
          if (shotState.pinned) return;
          setShotFocus(view.shot.id, partId, {});
        });
        node.addEventListener("mouseleave", () => {
          if (shotState.pinned) return;
          clearShotFocus();
        });
      }
    );
  }

  function closestShotRef(target) {
    const ref = target.closest ? target.closest(".figref") : null;
    return ref && ref.hasAttribute("data-shot") ? ref : null;
  }

  function bindShotRefs() {
    if (shotState.bound) return;
    shotState.bound = true;

    document.addEventListener("click", (event) => {
      const ref = closestShotRef(event.target);
      if (!ref) return;
      event.preventDefault();
      const shotId = ref.getAttribute("data-shot");
      const partId = ref.getAttribute("data-part");
      if (
        shotState.pinned &&
        shotState.shot === shotId &&
        shotState.part === partId
      )
        clearShotFocus();
      else setShotFocus(shotId, partId, { pinned: true, fromRef: true });
    });

    document.addEventListener("focusin", (event) => {
      const ref = closestShotRef(event.target);
      if (!ref || shotState.pinned) return;
      setShotFocus(
        ref.getAttribute("data-shot"),
        ref.getAttribute("data-part"),
        { fromRef: true }
      );
    });

    if (hoverCapable()) {
      document.addEventListener("mouseover", (event) => {
        const ref = closestShotRef(event.target);
        if (!ref || shotState.pinned) return;
        window.clearTimeout(shotState.hoverTimer);
        shotState.hoverTimer = window.setTimeout(() => {
          setShotFocus(
            ref.getAttribute("data-shot"),
            ref.getAttribute("data-part"),
            { fromRef: true }
          );
        }, HOVER_DELAY);
      });

      document.addEventListener("mouseout", (event) => {
        const ref = closestShotRef(event.target);
        if (!ref || shotState.pinned) return;
        window.clearTimeout(shotState.hoverTimer);
        clearShotFocus();
      });
    }

    // Scrolling and resizing can change which of the three behaviors is right
    // while a focus is held, exactly as they can for the teaser.
    let pending = 0;
    window.addEventListener(
      "scroll",
      () => {
        if (!pending && shotState.pinned) {
          pending = window.requestAnimationFrame(() => {
            pending = 0;
            if (shotState.part) placeShotFocus(false);
          });
        }
      },
      { passive: true }
    );
    window.addEventListener("resize", () => {
      if (pending) window.cancelAnimationFrame(pending);
      pending = window.requestAnimationFrame(() => {
        pending = 0;
        Object.keys(shotViews).forEach((id) => {
          reserveShotStatusHeight(shotViews[id]);
        });
        if (shotState.part) placeShotFocus(false);
      });
    });
  }

  /* --------------------------------------------------------- components */

  /* Each entry hydrates one `::: name` block from the Markdown. `mount` is the
     empty div the compiler left, `params` are the block's `key=value` arguments,
     and `numbers` are the figure and table numbers Python assigned to it. The
     roster here must match COMPONENTS in `report.py`, which is what makes an
     unknown block a build error rather than a blank space on the page. */
  const COMPONENTS = {
    teaser: function (mount, params, numbers) {
      createTeaser(mount, numbers.figure);
    },

    /* A view of the running application, taken from the position the markdown
       declares. The picture arrives in the payload as a data URI, like every
       other asset on this page, so the report stays one file. The position
       it was taken from stays in the markdown declaration and in
       `captures.json`; the page shows the picture and its caption alone. */
    screenshot: function (mount, params, numbers) {
      const shot = (DATA.screenshots || {})[params.id];
      if (!shot || !shot.src) {
        mount.appendChild(
          emptyNote(
            "<strong>No capture for <code>::: screenshot id=" +
              escapeHtml(params.id) +
              "</code>.</strong><br>The position is declared in " +
              "<code>docs/report/report.md</code>; the picture is taken from " +
              "it by<br><br><code>python scripts/generate_report.py --shots " +
              escapeHtml(params.id) +
              "</code>"
          )
        );
        return;
      }
      /* How much of the page this one is entitled to. A capture is a fixed
         number of CSS pixels and is never enlarged past them, so the width the
         browser was given is the width the figure wants: the block is told that
         number and the stylesheet spends no more of the column than it asks for.

         A portrait capture—a phone, held upright—is narrow enough to stand in
         the margin beside the text instead of interrupting it, which is what
         `widget-margin` asks for and what the stylesheet grants where the page
         is wide enough to hold both. A desktop capture is wider than the measure
         and takes the room a drawing takes. */
      const widget = mount.closest(".widget");
      if (widget && shot.width) {
        const inMargin = shot.width <= MARGIN_FIGURE_MAX;
        const shown = inMargin
          ? Math.round(shot.width * MARGIN_FIGURE_SCALE)
          : shot.width;
        widget.style.setProperty("--fig-width", shown + "px");
        widget.classList.add(inMargin ? "widget-margin" : "widget-wide");
      }
      const img = el("img", {
        class: "shot-img",
        src: shot.src,
        alt: shot.alt || shot.caption,
        // The intrinsic size in CSS pixels, so the page reserves the
        // right box before the picture decodes—and so no lazy loading is
        // needed, which on paper would risk printing an undecoded image.
        width: shot.width,
        height: shot.height,
      });
      /* A shot with declared parts is wrapped for the linking machinery: the
         overlay shares the picture's box, and both transform together inside
         the clip when a part is enlarged in place. A shot without parts stays
         a bare image. */
      const parts = shot.parts || [];
      let media = img;
      let overlay = null;
      let canvas = null;
      let clip = null;
      if (parts.length) {
        overlay = buildShotOverlay(shot);
        canvas = el("div", { class: "shot-canvas" }, [img, overlay.root]);
        clip = el("div", { class: "shot-clip" }, [canvas]);
        media = clip;
      }
      const children = [
        figureCaption("Figure", numbers.figure, shot.caption),
        el("div", { class: "shot-frame" }, [media]),
      ];
      let status = null;
      if (parts.length) {
        status = el("div", {
          class: "teaser-status shot-status",
          "aria-live": "polite",
        });
        children.push(status);
      }
      const figure = el("figure", { class: "figure shot" }, children);
      mount.appendChild(figure);
      if (parts.length) {
        const view = {
          shot: shot,
          figure: figure,
          clip: clip,
          canvas: canvas,
          svg: overlay.root,
          scrim: overlay.scrim,
          status: status,
          zoomed: false,
          figureLabel: "Figure " + numbers.figure,
        };
        shotViews[shot.id] = view;
        bindShotParts(view);
        renderShotStatus(view);
        reserveShotStatusHeight(view);
        bindShotRefs();
      }
    },

    /* The figure follows the space it is given: the drawing whose names come
       out largest in the column. The mid drawing needs 660 units, which is
       most windows; below that the compact one, scaled to fit.

       A measurement, not a breakpoint, because a breakpoint is a guess at this
       number and goes stale the moment a step is added to the spec. Height
       decides too, because the drawings scale: a mid drawing squeezed to 0.72
       of itself by a short window carries more than the compact one and reads
       worse, so the compact one is used instead.

       Both figures answer together. The prose promises them "at the same scale,
       so that the pipelines may be compared directly", and a page that drew one
       mid and the other compact would quietly break that comparison. */
    pipeline: function (mount, params, numbers) {
      let chart = null;
      let showing = null;

      function sizeFor() {
        const available = mount.clientWidth;
        // Before layout there is no width to measure; nothing is decided on a
        // zero, and the resize pass below settles it once there is a page.
        if (available <= 0) return "mid";

        /* The sizes all scale to the room, so the winner is not the one that
           carries the most but the one that still sets its names largest once
           fitted—and ties go to the one carrying more. It is a real question,
           not a formality: in a 980-unit column 768px tall, mid comes out at
           9.3px type and compact at 9.5px, so mid wins on a tie; give the same
           column a 900px window and compact grows to 11.2px while mid is still
           held at 10.9px by the same height, and compact takes it. */
        const options = SIZES.map((name) => {
          return {
            name: name,
            type: METRICS[name].TITLE_PX * fitScale(name, available),
          };
        });
        const best = options.reduce((top, option) => {
          return Math.max(top, option.type);
        }, 0);
        const winner = options.find((option) => {
          return option.type >= best * TIER_TYPE_TOLERANCE;
        });
        return winner ? winner.name : "compact";
      }

      function sync() {
        const wanted = sizeFor();
        if (chart && wanted === showing) {
          // Same drawing, new room: only the size it is rendered at changes.
          chart.refit();
          return;
        }
        if (chart) chart.destroy();
        showing = wanted;
        chart = createChart(mount, params.lane, numbers.figure, {
          size: wanted,
        });
      }

      sync();
      onViewportChange(sync);
    },

    /* The vocabulary itself, once, where the report first uses it: the
       perspectives a biography is turned into, in the order the paragraph above
       introduces them. Each description carries the id its references point at,
       so a phrase in the prose opens the entry that defines it. */
    conceptlegend: function (mount) {
      const list = el("dl", { class: "conceptlist" });
      (DATA.concepts || [])
        .filter((concept) => concept.legend)
        .forEach((concept) => {
          list.appendChild(
            el("dt", {}, [
              glyph(concept.path, "glyph big"),
              el("span", { text: concept.label }),
            ])
          );
          list.appendChild(
            el("dd", { id: "concept-" + concept.id, text: concept.blurb })
          );
        });
      mount.appendChild(list);
    },

    kindlegend: function (mount) {
      const list = el("dl", { class: "kindlist" });
      kindEntries().forEach((entry) => {
        list.appendChild(
          el("dt", {}, [
            el("span", {
              class: "swatch",
              style: "background:" + kindColor(entry[0]),
            }),
            el("span", { text: entry[1].label }),
          ])
        );
        list.appendChild(el("dd", { text: entry[1].description }));
      });
      mount.appendChild(list);
    },
  };

  /* ----------------------------------------------------- print appendix */

  /* On screen, what a step does and the record read out of its source are one
     click away in the step note. Paper has no click, so a printed report that
     stopped at the figures would be missing the material the figures are an
     index to. This builds that material as an appendix: every step, in the
     order the pipelines run them, with the step note's own content.

     It is print-only. On screen it would double the length of the page to say
     what the step note already says on demand, so the stylesheet hides it and the
     print rules bring it back. `?appendix=0` skips building it at all, for a
     PDF that is meant to stay short. */

  const APPENDIX_LETTER = "A";

  function appendixWanted() {
    const params = new URLSearchParams(window.location.search);
    const value = params.get("appendix");
    return value !== "0" && value !== "off" && value !== "false";
  }

  function appendixHeading(level, number, slug, title) {
    return el("h" + (level + 1), {
      id: slug,
      class: "sec sec-" + level,
      html:
        '<a class="secno" href="#' +
        slug +
        '">' +
        escapeHtml(number) +
        "</a><span>" +
        escapeHtml(title) +
        "</span>",
    });
  }

  const APPENDIX_COLUMNS = [
    "Step",
    "Description",
    "Input",
    "Output",
    "Model (effort)",
    "#Calls",
  ];

  /* The model a step calls and, in parentheses, the reasoning effort it asks
     of it: one cell, since the effort means nothing without the model. */
  function modelEffort(step) {
    if (!step.model) return "";
    const effort = step.effort ? " (" + bare(step.effort) + ")" : "";
    return "<code>" + escapeHtml(bare(step.model) + effort) + "</code>";
  }

  function renderStepAppendix() {
    const host = document.getElementById("report");
    if (!host || !appendixWanted()) return;

    /* Pipelines in the order the report draws them, which is the order the
       spec lists their steps in; the lane table's own key order is not it. */
    const columns = [];
    DATA.steps.forEach((step) => {
      if (!columns.includes(step.column)) columns.push(step.column);
    });
    if (!columns.length) return;

    const section = el("section", { class: "appendix" });
    section.appendChild(
      appendixHeading(1, APPENDIX_LETTER, "appendix-steps", "Step details")
    );
    /* The table is read against the pipeline charts, so the intro names
       them by number, as the LaTeX rendering does. */
    const cited = columns.map((laneId) => {
      const chart = charts.find((entry) => entry.lane === laneId);
      const label =
        "the " + DATA.lanes[laneId].label.toLowerCase() + " pipeline";
      return chart ? label + " (Figure " + chart.figure + ")" : label;
    });
    section.appendChild(
      el("p", {
        text:
          "The steps of " +
          cited.join(" and ") +
          ", one per row: description, input, output, model with " +
          "reasoning effort, and calls per run.",
      })
    );

    /* One table rather than an entry per step: a row is read across, and
       forty steps compare down a column, which forty paragraphs never let a
       reader do. The steps of each pipeline sit under a row naming it. */
    const table = el("table", { class: "data steps-table" });
    table.appendChild(
      el("thead", {}, [
        el(
          "tr",
          {},
          APPENDIX_COLUMNS.map((title) => el("th", { text: title }))
        ),
      ])
    );
    const tbody = el("tbody");
    columns.forEach((laneId) => {
      tbody.appendChild(
        el("tr", { class: "lane-row" }, [
          el("th", {
            colspan: String(APPENDIX_COLUMNS.length),
            text: DATA.lanes[laneId].label,
          }),
        ])
      );
      stepsOf(laneId).forEach((step) => {
        const record = stepRecord(step);
        /* The step's name carries the underline in its kind's color, as a
           reference to it in the text does, so the row is read against the
           charts without a number. */
        const name = el("span", {
          class: "step-name",
          "data-kind": step.kind || "",
          text: step.label,
        });
        tbody.appendChild(
          el("tr", { class: "step-row", id: "appendix-" + step.id }, [
            el("th", { scope: "row" }, [name]),
            el("td", { text: stepDescription(step) }),
            el("td", { html: record.input }),
            el("td", { html: record.output }),
            el("td", { html: modelEffort(step) }),
            el("td", { html: record.calls }),
          ])
        );
      });
    });
    table.appendChild(tbody);
    section.appendChild(el("div", { class: "table-scroll" }, [table]));

    host.appendChild(section);
  }

  /* A `<details>` is a promise that the content is one click away. Paper cannot
     take the click, so every disclosure on the page is opened before printing
     and put back afterwards—the reader who printed by accident gets their page
     back as they left it. `scripts/export_report_pdf.mjs` does the same thing
     itself, because printing through the DevTools protocol never fires these
     events. */
  function bindPrintDisclosure() {
    let reopened = [];
    window.addEventListener("beforeprint", () => {
      reopened = Array.prototype.filter.call(
        document.querySelectorAll("details"),
        (node) => {
          return !node.open;
        }
      );
      reopened.forEach((node) => {
        node.open = true;
      });
    });
    window.addEventListener("afterprint", () => {
      reopened.forEach((node) => {
        node.open = false;
      });
      reopened = [];
    });
  }

  /* --------------------------------------------------------- page chrome */

  function renderMetaRow() {
    const host = document.getElementById("meta-row");
    if (!host) return;
    // The report is versioned by date and by nothing else. A commit and a
    // build time answer "which build is this"; the reader at the top of the
    // page is asking "how current is what I am about to read".
    host.appendChild(
      el("span", { class: "chip" }, [
        el("span", {
          text: "Version of " + (DATA.version || DATA.generated_at),
        }),
      ])
    );
  }

  /* The rail mirrors the heading tree the Markdown produced, so it cannot list
     a section that is not in the document or miss one that is. */
  function renderRail() {
    const host = document.getElementById("rail-nav");
    const sections = (DATA.report && DATA.report.sections) || [];
    if (!host) return;
    if (!sections.length) {
      document.getElementById("rail").hidden = true;
      return;
    }

    const links = [];
    function add(items, depth) {
      items.forEach((item) => {
        const link = el("a", {
          class: "rail-link depth-" + depth,
          href: "#" + item.slug,
        });
        link.appendChild(el("span", { class: "rail-no", text: item.number }));
        link.appendChild(el("span", { text: item.title }));
        host.appendChild(link);
        links.push({ link: link, slug: item.slug });
        if (item.children && item.children.length) {
          add(item.children, depth + 1);
        }
      });
    }
    add(sections, 1);

    const targets = links
      .map((entry) => {
        return {
          link: entry.link,
          node: document.getElementById(entry.slug),
        };
      })
      .filter((entry) => {
        return entry.node;
      });

    // Scroll spy: mark the last heading above the reading line. Cheap enough to
    // run on scroll for a document of this size, and it avoids the flicker an
    // IntersectionObserver gives on long sections with no visible heading.
    let raf = 0;
    function spy() {
      raf = 0;
      const line = window.innerHeight * 0.28;
      let active = targets[0];
      targets.forEach((entry) => {
        if (entry.node.getBoundingClientRect().top <= line) active = entry;
      });
      targets.forEach((entry) => {
        entry.link.classList.toggle("current", entry === active);
      });
    }
    window.addEventListener(
      "scroll",
      () => {
        if (!raf) raf = window.requestAnimationFrame(spy);
      },
      { passive: true }
    );
    spy();
  }

  /* ------------------------------------------------- contents button */

  /* Below the rail breakpoint the contents section is plain document content:
     it scrolls past the reader once and is gone. This keeps it one tap away—a
     button in the corner that appears exactly when that section leaves the
     viewport, and a panel holding the same list, cloned rather than rebuilt so
     the two can never drift apart. Above the breakpoint the rail is already on
     screen and the stylesheet keeps both out of the way. */
  function renderTocButton() {
    const inline = document.querySelector(".toc");
    const fab = document.getElementById("toc-fab");
    const pop = document.getElementById("toc-pop");
    const list = inline && inline.querySelector(".toc-list");
    if (!inline || !fab || !pop || !list) return;

    pop.appendChild(list.cloneNode(true));

    function close() {
      pop.hidden = true;
      fab.setAttribute("aria-expanded", "false");
    }

    fab.addEventListener("click", () => {
      if (fab.getAttribute("aria-expanded") === "true") {
        close();
        return;
      }
      pop.hidden = false;
      fab.setAttribute("aria-expanded", "true");
    });

    // Following a link is a jump away from here, so the panel has done its job.
    pop.addEventListener("click", (event) => {
      if (event.target.closest && event.target.closest("a")) close();
    });

    document.addEventListener("click", (event) => {
      if (pop.hidden) return;
      if (fab.contains(event.target) || pop.contains(event.target)) return;
      close();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") close();
    });

    // While the contents section is on screen the button would only point at
    // what the reader is already looking at. A hidden `.toc` measures as a zero
    // rectangle, so this stays false at the widths where the rail is a column.
    let raf = 0;
    function sync() {
      raf = 0;
      const gone = inline.getBoundingClientRect().bottom < 0;
      if (fab.hidden !== gone) return;
      fab.hidden = !gone;
      if (!gone) close();
    }
    function schedule() {
      if (!raf) raf = window.requestAnimationFrame(sync);
    }
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule, { passive: true });
    sync();
  }

  /* -------------------------------------------- notes and citations */

  /* Several kinds of marker are read the same way. An inline note is authored
     once and printed as a numbered list closing its section; a citation is
     numbered by first use and printed in the references. Every marker is a real
     link into that printed text, so all of them work with this file absent and
     on paper.

     What this adds is the screen reading: the marker opens the text it points
     at in a popover, which keeps an aside—or a reference the reader has no
     reason to have memorized—off the measure until it is asked for. The notes
     list is withdrawn once that is possible; the reference list stays, which a
     reader expects to find at the end whether or not they ever opened a
     marker.

     A citation's popover carries the entry's DOI as a live link, so following a
     reference costs the reader neither their place in the sentence nor a trip
     to the back of the document.

     The popover copies the item it points at rather than carrying its own copy
     of the text, so the two renderings cannot drift apart. It is positioned in
     document coordinates, so it stays on its marker while the reader
     scrolls. */
  const POP_REF = ".noteref, .refref, .cref";

  function renderPopovers() {
    const refs = document.querySelectorAll(
      ".report .noteref, .report .refref, .report .cref"
    );
    if (!refs.length) return;
    if (document.querySelector(".report .noteref")) {
      document.body.classList.add("has-note-pop");
    }

    const number = el("p", { class: "note-pop-no" });
    const body = el("div", { class: "note-pop-body" });
    const pop = el(
      "aside",
      { class: "note-pop", id: "note-pop", role: "note", hidden: "" },
      [number, body]
    );
    document.body.appendChild(pop);
    let open = null;

    function close() {
      if (!open) return;
      open.classList.remove("open");
      open.setAttribute("aria-expanded", "false");
      open = null;
      pop.hidden = true;
    }

    // Below the marker by preference, above it when the viewport has no room
    // there, and never past either edge of the measure.
    function place(ref) {
      const rect = ref.getBoundingClientRect();
      const width = pop.offsetWidth;
      const height = pop.offsetHeight;
      const margin = 12;
      const below = rect.bottom + 8;
      const above = rect.top - height - 8;
      const fitsBelow = below + height + margin <= window.innerHeight;
      const left = Math.max(
        margin,
        Math.min(
          rect.left + rect.width / 2 - width / 2,
          window.innerWidth - width - margin
        )
      );
      pop.style.left = left + window.scrollX + "px";
      pop.style.top =
        (fitsBelow || above < margin ? below : above) + window.scrollY + "px";
    }

    function show(ref) {
      const item = document.getElementById(
        (ref.getAttribute("href") || "").slice(1)
      );
      if (!item) return false;
      const text = item.querySelector(".pop-body");
      close();
      number.textContent =
        ref.getAttribute("data-pop-label") || (ref.textContent || "").trim();
      body.innerHTML = text ? text.innerHTML : item.innerHTML;
      pop.hidden = false;
      place(ref);
      ref.classList.add("open");
      ref.setAttribute("aria-expanded", "true");
      open = ref;
      return true;
    }

    Array.prototype.forEach.call(refs, (ref) => {
      ref.setAttribute("aria-expanded", "false");
      ref.addEventListener("click", (event) => {
        // A modified click is a request to open the link, not to read here.
        if (event.metaKey || event.ctrlKey || event.shiftKey) return;
        if (open === ref) {
          event.preventDefault();
          close();
          return;
        }
        // Only swallow the jump if there is something to show instead.
        if (show(ref)) event.preventDefault();
      });
    });

    document.addEventListener("click", (event) => {
      if (!open) return;
      const target = event.target;
      if (pop.contains(target)) return;
      if (target.closest && target.closest(POP_REF)) return;
      close();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") close();
    });

    window.addEventListener(
      "resize",
      () => {
        if (open) place(open);
      },
      { passive: true }
    );
  }

  /* ------------------------------------------------- margin figures */

  /* A figure standing in the margin keeps beside the text it was declared in
     and stays in view while that text is read, instead of arriving with the
     paragraph and leaving with it.

     The figure runs a little ahead of its paragraph: it may stand as much as
     its own height above its place in the document, so that it is in view,
     as completely as the viewport allows, from the moment the paragraph is.
     A figure that fits the viewport is held whole: by its bottom edge while
     its place is still low in the viewport, beside its place as that rises,
     and by its top edge once its place has passed the pin line. A figure
     taller than the viewport cannot be held whole, so it is held by its top
     edge while its place is below the pin line, scrolls with the text as its
     place passes through, which brings its bottom into view, and is held by
     its bottom edge from there on. It stays until the next margin figure takes
     its place, until a wide block or a section heading pushes it off, or,
     where there is nothing further, to the end of the report.

     The stylesheet does the placing and the holding—the widget is an anchor
     without height in the flow, the band is positioned from it into the
     margin, starting as far above the anchor as the figure may run ahead, and
     the body inside the band is `position: sticky` with the same inset at top
     and bottom, which the band's height bounds—and this code only measures:
     where each figure's place is, how far it may run ahead, how far its band
     reaches, how far under the edge it pins, and, on scroll, how far the next
     figure has taken over. Two things the figure no longer reserves in the
     flow are made up for here: a wide block that would start inside a
     figure's own height is moved below it, and the report is padded by
     however far the last figure hangs past its end.

     Nothing here applies where the figure is not in the margin: the band is
     sized only while it is positioned there, and the print rules release it. */
  const PIN_OFFSET = 20; // CSS pixels between the viewport's edge and a pinned figure
  const READING_LINE = 0.28; // of the viewport: where the text being read is, as the rail assumes
  const TAKEOVER_SLACK = 40; // CSS pixels a handover must be undone by before it reverses
  const COVER_ENTER = 60; // of overlap before a figure counts as covered by the next
  const COVER_LEAVE = 20; // of overlap left before it counts as uncovered again
  const FIGURE_GAP = 32; // kept between a figure and a wide block or heading

  const marginState = {
    bands: [], // one per margin figure, in document order
    active: false, // whether the figures currently stand in the margin
  };

  function marginBandOf(node) {
    return (
      marginState.bands.find((band) => {
        return band.body.contains(node);
      }) || null
    );
  }

  /* Whether a figure is showing: one where it is, zero once the next figure
     has taken its place. The state, not the crossfade in progress. */
  function marginFadeOf(node) {
    const band = marginBandOf(node);
    return band && marginState.active ? band.fade : 1;
  }

  /* Scroll so that a margin figure's place in the document is at the pin
     line, which shows the figure from its top and uncovered. For a pinned
     figure, scrolling to where it currently is would move nothing. */
  function revealMarginFigure(node) {
    const band = marginBandOf(node);
    if (!band || !marginState.active) return false;
    window.scrollTo({
      top: Math.max(0, band.top - PIN_OFFSET),
      behavior: reducedMotion() ? "auto" : "smooth",
    });
    return true;
  }

  function bindMarginFigures() {
    const widgets = Array.prototype.slice.call(
      document.querySelectorAll(".report > .widget-margin")
    );
    if (!widgets.length) return;
    const report = widgets[0].parentNode;

    marginState.bands = widgets.map((widget) => {
      const body = el("div", { class: "margin-body" });
      while (widget.firstChild) body.appendChild(widget.firstChild);
      const band = el("div", { class: "margin-band" }, [
        el("div", { class: "margin-space" }),
        body,
      ]);
      widget.appendChild(band);
      return {
        widget: widget,
        band: band,
        body: body,
        top: 0, // the figure's place in the document, in page pixels
        height: 0, // the figure's own height
        text: 0, // the height of the block declared under it: its paragraph
        lead: 0, // how far above its place the figure may stand
        reach: 0, // the height of the stretch it serves, from its place on
        end: 0, // where its band ends, in page pixels
        next: null, // the band that takes this one's place, if any
        taken: false, // whether the next figure has taken over from this one
        covered: false, // whether the next figure's body covers this one's
        fade: 1, // one while shown, zero while hidden: the state, not the animation
      };
    });
    const bands = marginState.bands;

    function setShown(band, shown) {
      const value = shown ? 1 : 0;
      if (band.fade === value) return;
      band.fade = value;
      band.body.classList.toggle("is-covered", !shown);
    }

    /* What bounds a band, in document order: a wide block and the appendix,
       which claim the whole width, and a section heading, which starts a
       stretch of text the figure was not placed beside. A band ends at the
       next of these, and starts no higher than the previous one's bottom. */
    function stops() {
      const scrollY = window.scrollY;
      const nodes = report.querySelectorAll(
        ":scope > .widget-wide, :scope > .appendix, :scope > h2.sec"
      );
      return Array.prototype.map.call(nodes, (node) => {
        const box = node.getBoundingClientRect();
        return {
          node: node,
          at: box.top + scrollY,
          bottom: box.bottom + scrollY,
          wide: !node.classList.contains("sec"),
        };
      });
    }

    function release() {
      bands.forEach((band) => {
        band.band.style.removeProperty("--band-height");
        band.band.style.removeProperty("--lead");
        band.body.style.removeProperty("--pin");
        setShown(band, true);
      });
      stops().forEach((stop) => {
        stop.node.style.removeProperty("--clear");
      });
      report.style.removeProperty("--tail");
    }

    /* Where the figures are and where the bands end. The wide blocks are
       measured with nothing moved below a figure yet; one that starts inside a
       figure's own height is then moved, and everything after it with it, so
       the places are measured again until nothing more moves. */
    function measure() {
      const scrollY = window.scrollY;
      bands.forEach((band) => {
        band.top = band.widget.getBoundingClientRect().top + scrollY;
        band.height = band.body.offsetHeight;
        const under = band.widget.nextElementSibling;
        band.text = under ? under.offsetHeight : 0;
      });
      const found = stops();
      let moved = false;
      bands.forEach((band) => {
        found.forEach((stop) => {
          if (!stop.wide || stop.at <= band.top) return;
          const clear = band.top + band.height + FIGURE_GAP - stop.at;
          if (clear <= 0) return;
          const already =
            parseFloat(stop.node.style.getPropertyValue("--clear")) || 0;
          stop.node.style.setProperty("--clear", already + clear + "px");
          moved = true;
        });
      });
      return moved ? null : found;
    }

    function layout() {
      release();
      marginState.active =
        window.getComputedStyle(bands[0].band).position === "absolute";
      if (!marginState.active) return;
      let found = measure();
      for (let pass = 0; !found && pass < 3; pass += 1) found = measure();
      if (!found) found = stops();
      const scrollY = window.scrollY;
      const viewport = window.innerHeight;
      const reportBox = report.getBoundingClientRect();
      const reportStart = reportBox.top + scrollY;
      const reportEnd = reportBox.bottom + scrollY;
      bands.forEach((band, index) => {
        const next = bands[index + 1] || null;
        // The figure may run ahead of its place by its own height, but not
        // over whatever stands above it in the margin.
        let above = reportStart;
        found.forEach((stop) => {
          if (stop.at < band.top && stop.bottom > above) above = stop.bottom;
        });
        band.lead = Math.max(
          0,
          Math.min(band.height, band.top - above - FIGURE_GAP)
        );
        // The band lasts until the next figure has taken this one's place,
        // which is complete by the time that one's own place has passed the
        // pin line, or until something else claims the margin.
        let end = next ? next.top + band.height : reportEnd;
        found.forEach((stop) => {
          if (stop.at > band.top && stop.at < end) end = stop.at;
        });
        band.reach = Math.max(band.height, end - band.top);
        band.end = band.top + band.reach;
        // Whatever ends the band, a next figure that arrives before it does
        // is what takes this one's place.
        band.next = next && next.top < band.end ? next : null;
        // One inset for both edges: with a figure that fits, it keeps the
        // whole figure inside the viewport; with one that does not, it is
        // negative by the excess, so the top edge is held under the
        // viewport's top and the bottom edge under its bottom.
        const pin = Math.min(PIN_OFFSET, viewport - PIN_OFFSET - band.height);
        band.band.style.setProperty("--lead", band.lead + "px");
        band.band.style.setProperty(
          "--band-height",
          band.lead + band.reach + "px"
        );
        band.body.style.setProperty("--pin", pin + "px");
      });
      const last = bands[bands.length - 1];
      const tail = last.top + last.height - reportEnd;
      if (tail > 0) report.style.setProperty("--tail", tail + "px");
      decide();
      report.classList.add("is-settled");
    }

    /* Which figures show. The next figure takes over once the reader is done
       with this one's paragraph—its bottom has passed the reading line—and
       this one is hidden once the next actually covers it on screen: a figure
       declared far below stands clear at first and covers this one as it
       rises, while one declared close by stands in the same place from the
       start and the two simply trade places. Until the paragraph is done the
       next figure is hidden, wherever it stands.

       Each is a decision, not a dial: a figure is shown or hidden, and the
       stylesheet carries the change as a crossfade of fixed duration, so a
       reader who stops scrolling is never left between two figures. A
       decision reverses only once the scroll has moved a little past the
       point that made it, so a reader lingering there does not see the two
       figures flicker. */
    function decide() {
      if (!marginState.active) return;
      const viewport = window.innerHeight;
      const line = viewport * READING_LINE;
      const shown = bands.map(() => {
        return true;
      });
      bands.forEach((band, index) => {
        if (!band.next) {
          band.taken = false;
          band.covered = false;
          return;
        }
        const done = band.widget.getBoundingClientRect().top + band.text;
        band.taken = band.taken
          ? done < line + TAKEOVER_SLACK
          : done < line - TAKEOVER_SLACK;
        const bottom = Math.min(
          band.body.getBoundingClientRect().bottom,
          viewport
        );
        const overlap = bottom - band.next.body.getBoundingClientRect().top;
        band.covered = band.covered
          ? overlap > COVER_LEAVE
          : overlap > COVER_ENTER;
        if (band.taken && band.covered) shown[index] = false;
        if (!band.taken) shown[index + 1] = false;
      });
      bands.forEach((band, index) => {
        setShown(band, shown[index]);
      });
    }

    let scrolling = 0;
    window.addEventListener(
      "scroll",
      () => {
        if (!scrolling) {
          scrolling = window.requestAnimationFrame(() => {
            scrolling = 0;
            decide();
          });
        }
      },
      { passive: true }
    );

    // The places move whenever the text reflows above a figure or a figure
    // changes height—a status strip reserved, a window resized—so the bands
    // are measured again when the report or a figure changes size.
    let pending = 0;
    function schedule() {
      if (!pending) {
        pending = window.requestAnimationFrame(() => {
          pending = 0;
          layout();
        });
      }
    }
    window.addEventListener("resize", schedule, { passive: true });
    if (window.ResizeObserver) {
      const observer = new ResizeObserver(schedule);
      observer.observe(report);
      bands.forEach((band) => {
        observer.observe(band.body);
      });
    }
    layout();
  }

  /* --------------------------------------------------------------- init */

  /* Hydrate the compiled Markdown. Document order matters: the figure and table
     numbers were assigned in that order in Python, and the charts read cleanest
     when the earlier pipeline is laid out first. */
  function hydrate() {
    const mounts = document.querySelectorAll(".widget[data-component]");
    Array.prototype.forEach.call(mounts, (widget) => {
      const name = widget.getAttribute("data-component");
      const build = COMPONENTS[name];
      const host = widget.querySelector(".widget-mount");
      const fallback = widget.querySelector(".widget-fallback");
      if (fallback) fallback.remove();
      if (!build || !host) {
        widget.appendChild(
          emptyNote(
            "No renderer for <code>::: " +
              escapeHtml(name) +
              "</code>. The build should have rejected this block."
          )
        );
        return;
      }
      const params = {};
      Array.prototype.forEach.call(widget.attributes, (attribute) => {
        if (attribute.name.indexOf("data-") !== 0) return;
        params[attribute.name.slice(5)] = attribute.value;
      });
      build(host, params, {
        figure: Number(widget.getAttribute("data-figure") || 1),
        table: Number(widget.getAttribute("data-table") || 1),
      });
    });
  }

  bindStepTip();
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    clearTeaserFocus();
    closeStepTip();
  });

  renderMetaRow();
  hydrate();
  renderStepAppendix();
  renderRail();
  renderTocButton();
  renderPopovers();
  bindPrintDisclosure();
  bindRefKeys();
  bindStepRefs();
  bindMarginFigures();

  // The page is fully built. `scripts/export_report_pdf.mjs` waits for this
  // before printing, so a PDF can never catch the report half-hydrated.
  document.documentElement.setAttribute("data-report-ready", "1");
})();
