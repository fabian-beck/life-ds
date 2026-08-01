/* Technical report—computed content and interaction.
   The page is a pure function of window.PIPELINE, which the Python build emits.
   Layout runs client-side so filters can re-flow the chart.

   The document body is compiled from Markdown and arrives already written; this
   file only fills the holes left in it. Every `div.widget[data-component]` the
   Markdown placed is hydrated by the matching entry in COMPONENTS, in document
   order, so *where* a figure appears is an authoring decision while *what* it
   contains is a build-time computation. Adding a section to the report never
   touches this file; adding a new kind of computed block means one COMPONENTS
   entry here and one in `report.py`.

   Both pipelines are drawn, as two subsections rather than two tabs, so the
   report reads straight through and either chart can be cited from anywhere in
   the prose. Each chart is an independent instance with its own filters, search
   and selection; the step drawer is shared, and opening it from one chart clears
   the other's selection. Color encodes the step kind and nothing else.

   The chart is a layered DAG, not a sequence. A step's layer is the longest
   path of real data dependencies reaching it, so steps drawn side by side are
   genuinely independent—the map branch and the network branch of the meta
   story really do run without seeing each other. Only edges the spec declares
   directly are drawn—one a longer chain already implies is left out there, so
   the chart never carries a line beside a strand that says the same thing.
   Files a step writes are drawn inside its node; files that arrive from the
   other pipeline become source nodes, since nothing in this chart produces them.

   The vertical axis is the dependency graph; the horizontal axis is free, and
   `spec.GROUPS` spends it on meaning. Steps of one concern—plan the image
   searches, run them, match the results—are aligned and banded, so a job that
   takes three layers reads as one vertical strand instead of drifting across the
   chart. Alignment holds only where a group is continuous: a member several
   layers below the rest is placed on its own. Positions are continuous and
   relaxed toward the center, not slots in a grid. */

(function () {
  "use strict";

  const DATA = window.PIPELINE;
  const SVG_NS = "http://www.w3.org/2000/svg";

  /* Chart geometry, in SVG user units, at three levels of detail.

     They are the same graph—same layers, same order, same bands—drawn with
     more or less written inside a node, and sized to match:

       full     the step's name, the script it lives in, its kind, the model it
                calls and what it writes. 990 units.
       mid      the name, the kind and the model. No script, no writes. 660.
       compact  the name. 398.

     A reduced drawing is not the full one shrunk. Fitting a 990-unit figure
     into a 350-unit column would put 13px type on screen at 4px, which is not
     a reduced figure but an unreadable one. Each is a drawing with less in it,
     laid out at its own size, so what survives stays legible; the full one is
     always a press away in the modal.

     Three rather than two because the gap between them is where most windows
     are. A 1010-unit column takes the full chart and a 350-unit one takes the
     compact, but the 650-to-950 range in between—a tablet, a half-screen
     window, a laptop beside the contents rail—had to take the compact drawing
     and a great deal of white space around it. */
  const METRICS = {
    full: {
      TITLE_PX: 13, // the step-name type; mirrors style.css
      RAIL_W: 58,
      RAIL_GAP: 20, // rule to node: where the layer number is written
      RAIL_DX: 7,
      RAIL_DY: 13,
      NODE_W: 268,
      NODE_H: 66,
      FILE_H: 15,
      ART_W: 214,
      ART_H: 38,
      COL_GAP: 26,
      LAYER_GAP: 52,
      MARGIN_CH: 26, // side channels for edges that skip a layer
      PAD: 12,
      BAND_PAD: 9,
      BAND_HEAD: 20, // room for a group band's label above its first step
    },
    mid: {
      TITLE_PX: 11,
      RAIL_W: 40,
      RAIL_GAP: 14,
      RAIL_DX: 6,
      RAIL_DY: 11,
      NODE_W: 176,
      NODE_H: 44,
      FILE_H: 0, // files are not drawn at this size
      ART_W: 140,
      ART_H: 30,
      COL_GAP: 20,
      LAYER_GAP: 30,
      MARGIN_CH: 18,
      PAD: 8,
      BAND_PAD: 7,
      BAND_HEAD: 19, // the group label still fits above the first step here
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
      FILE_H: 0,
      ART_W: 92,
      ART_H: 24,
      COL_GAP: 12,
      LAYER_GAP: 26,
      MARGIN_CH: 12,
      PAD: 6,
      BAND_PAD: 5,
      BAND_HEAD: 8, // no band label to leave room for, only the band's corner
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

  // Largest first: the reduced sizes, in the order they are offered a column.
  const SIZES = ["full", "mid", "compact"];

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

  // Live chart instances, so the shared drawer can clear the selection in the
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

  function tableScroll(table) {
    return el("div", { class: "table-scroll" }, [table]);
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
    step._search = [
      step.label,
      step.script,
      step.function,
      step.phase || "",
      step.spec_summary || "",
      (step.summary && step.summary.what_it_does) || "",
      (step.summary && step.summary.why_this_design) || "",
      ((step.summary && step.summary.constraints) || []).join(" "),
      (step.schemas || []).join(" "),
      (step.prompts || [])
        .map((prompt) => {
          return (prompt.segments || [])
            .map((segment) => {
              return segment.text;
            })
            .join(" ");
        })
        .join(" "),
    ]
      .join(" ")
      .toLowerCase();
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

  // The drawer builds its rows as markup, so the same mark is needed as a
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

  // What an artifact is called where it is drawn. The concept is the wider
  // family it belongs to and is printed under the name only where the two
  // differ—"Ego network", of the social network; "Portrait", of the imagery.
  function artifactConceptLine(artifact) {
    const concept = conceptOf(artifact);
    if (!concept || concept.label === artifact.label) return "";
    return concept.label;
  }

  /* -------------------------------------------------- pipeline chart */

  /* One interactive chart, mounted into `host` and owning its own filter state.

     Everything from here to the end of `createChart` is per-instance: the two
     pipelines are drawn side by side in the document, and a filter applied to
     one must not re-flow the other. The layout itself is unchanged—the layer
     rule, the group blocks and the edge routing are the same code that drew the
     single tabbed chart—it simply closes over an instance `state` and instance
     DOM nodes instead of the page's.

     `options.size` picks the level of detail—"full", "mid" or "compact". The
     two reduced sizes drop the toolbar, the artifact lines and, at compact, the
     group labels and everything written inside a node but its name; they are
     scaled to the column rather than scrolled sideways. What they drop is
     detail, never structure—the reader still sees every step, every dependency
     and every band, and `options.expandable` puts the full version one press
     away in the modal. */
  function createChart(host, laneId, figureNumber, options) {
    const settings = options || {};
    const size = settings.size || "full";
    const M = METRICS[size];
    // Two questions get asked of the size often enough to name: whether this is
    // a drawing that scales to its column, and whether it carries only the name.
    const reduced = size !== "full";
    const compact = size === "compact";
    // Declared up front so `select` can name the instance the drawer belongs to
    // before the instance is finished being built.
    const instance = { lane: laneId, size: size, host: host };
    const state = {
      tab: laneId,
      kinds: new Set(Object.keys(DATA.kinds)),
      showShared: true,
      // The files are the first thing to go: they are the widest text in a node
      // and a whole extra column of source boxes beside it.
      showArtifacts: !reduced,
      query: "",
      selected: null,
    };

    const lane = DATA.lanes[laneId];
    const wrapCache = {}; // step id → the lines a reduced node prints
    let naturalSize = null; // the drawing's own size, in SVG user units
    const flow = svg("svg", {
      class: "flow" + (reduced ? " flow-reduced flow-" + size : ""),
      role: "img",
      "aria-label": "Flow chart of the " + lane.label + " pipeline",
    });
    const hint = el("p", { class: "hint" });
    // Named for the element rather than for the helper, which the drawing
    // routine below calls to refill it.
    const captionNode = el("figcaption", { class: "cap cap-figure" });
    const search = el("input", {
      class: "search",
      type: "search",
      placeholder: "Search steps, prompts, schemas…",
      "aria-label": "Search the " + lane.label + " pipeline",
    });
    const filters = el("div", { class: "filters" });

    function stepsInTab() {
      return DATA.steps.filter((step) => {
        return step.column === state.tab;
      });
    }

    function matchesFilters(step) {
      if (!state.kinds.has(step.kind)) return false;
      if (!state.showShared && step.lane === "shared") return false;
      return true;
    }

    function matchesQuery(step) {
      if (!state.query) return true;
      return step._search.indexOf(state.query) !== -1;
    }

    /* ---------------------------------------------------------- toolbar */

    function renderToolbar() {
      clear(filters);

      Object.entries(DATA.kinds).forEach((entry) => {
        const kind = entry[0];
        const info = entry[1];
        const button = el("button", {
          class: "toggle",
          type: "button",
          "aria-pressed": state.kinds.has(kind) ? "true" : "false",
          title: info.description,
          onclick: function () {
            if (state.kinds.has(kind)) state.kinds.delete(kind);
            else state.kinds.add(kind);
            button.setAttribute(
              "aria-pressed",
              state.kinds.has(kind) ? "true" : "false"
            );
            draw();
          },
        });
        button.appendChild(
          el("span", {
            class: "swatch",
            style: "background:" + kindColor(kind),
          })
        );
        button.appendChild(el("span", { text: info.label }));
        filters.appendChild(button);
      });

      const shared = el("button", {
        class: "toggle",
        type: "button",
        "aria-pressed": state.showShared ? "true" : "false",
        title:
          "Steps that belong to shared subsystems rather than one pipeline.",
        text: "Shared subsystems",
        onclick: function () {
          state.showShared = !state.showShared;
          shared.setAttribute(
            "aria-pressed",
            state.showShared ? "true" : "false"
          );
          draw();
        },
      });
      filters.appendChild(shared);

      const artifacts = el("button", {
        class: "toggle",
        type: "button",
        "aria-pressed": state.showArtifacts ? "true" : "false",
        title:
          "Show what each step writes, and what this pipeline reads from the " +
          "other one.",
        text: "Data",
        onclick: function () {
          state.showArtifacts = !state.showArtifacts;
          artifacts.setAttribute(
            "aria-pressed",
            state.showArtifacts ? "true" : "false"
          );
          draw();
        },
      });
      filters.appendChild(artifacts);
    }

    /* ------------------------------------------------------------ chart */

    /* Resolve a step's dependencies against the *visible* set. A filtered-out
       step must not break the chain, so its own dependencies are inherited and
       the resulting edge is marked indirect and drawn dashed. */
    function resolveDeps(step, visibleIds, seen) {
      const out = [];
      (step.depends_on || []).forEach((dep) => {
        const parent = stepById[dep.on];
        if (!parent) return;
        if (visibleIds.has(dep.on)) {
          out.push({ from: dep.on, data: dep.data, indirect: false });
          return;
        }
        if (seen.indexOf(dep.on) !== -1) return;
        resolveDeps(parent, visibleIds, seen.concat([dep.on])).forEach(
          (edge) => {
            out.push({ from: edge.from, data: edge.data, indirect: true });
          }
        );
      });
      // One edge per source; keep the first (most direct) label.
      const unique = [];
      const taken = new Set();
      out.forEach((edge) => {
        if (taken.has(edge.from)) return;
        taken.add(edge.from);
        unique.push(edge);
      });
      return unique;
    }

    function buildGraph() {
      const steps = stepsInTab().filter(matchesFilters);
      const visibleIds = new Set(
        steps.map((step) => {
          return step.id;
        })
      );

      const parents = {};
      steps.forEach((step) => {
        parents[step.id] = resolveDeps(step, visibleIds, [step.id]);
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

      // A file read but never written in this pipeline comes from the other one;
      // it becomes a source node so the hand-off is visible rather than implied.
      const sources = {};
      if (state.showArtifacts) {
        const produced = new Set();
        steps.forEach((step) => {
          (step.outputs || []).forEach((id) => {
            produced.add(id);
          });
        });
        steps.forEach((step) => {
          (step.inputs || []).forEach((id) => {
            if (produced.has(id) || !artifactById[id]) return;
            if (!sources[id])
              sources[id] = { artifact: artifactById[id], to: [] };
            sources[id].to.push(step.id);
          });
        });
      }

      // Source files sit one layer above their earliest reader rather than all at
      // the top: a file only needed by the last step should be read as arriving
      // late, not as an input to the whole pipeline.
      let shift = 0;
      Object.values(sources).forEach((source) => {
        const earliest = Math.min.apply(
          null,
          source.to.map((id) => {
            return layerOf[id];
          })
        );
        source.layer = earliest - 1;
        if (source.layer < 0) shift = 1;
      });
      if (shift) {
        steps.forEach((step) => {
          layerOf[step.id] += 1;
        });
        Object.values(sources).forEach((source) => {
          source.layer += 1;
        });
      }

      return {
        steps: steps,
        parents: parents,
        layerOf: layerOf,
        sources: sources,
      };
    }

    function nodeHeight(step) {
      const files = state.showArtifacts ? (step.outputs || []).length : 0;
      return M.NODE_H + (files ? 6 + files * M.FILE_H : 0);
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
          const groupId = node.type === "step" ? groupOfStep[node.id] : null;
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
          const groupId = node.type === "step" ? groupOfStep[node.id] : null;
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
              near: [],
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
       single vertical strand.

       Stage one places the blocks: group runs and lone nodes alike, each a rigid
       rectangle with one x for every layer it crosses. Positions are continuous,
       not slots in a grid. A leftmost packing gives a feasible start, then blocks
       are relaxed toward the average position of their graph neighbors, each one
       clamped to the room its neighbors in every layer it occupies actually
       leave. That keeps the arrangement valid at every step while letting sparse
       layers center themselves under the layers they feed.

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
      // Who sits either side of a block, per layer: the only constraints there
      // are, and they never change, since the order does not.
      const bounds = [];
      perLayer.forEach((list) => {
        list.forEach((block, index) => {
          if (index) bounds.push([list[index - 1], block]);
        });
      });

      const nodeById = {};
      rows.forEach((row) => {
        row.forEach((node) => {
          nodeById[node.id] = node;
        });
      });
      function connect(a, b) {
        if (!a || !b || a === b) return;
        if (a.near.indexOf(b) === -1) a.near.push(b);
        if (b.near.indexOf(a) === -1) b.near.push(a);
      }
      graph.steps.forEach((step) => {
        (graph.parents[step.id] || []).forEach((edge) => {
          const from = nodeById[edge.from];
          const to = nodeById[step.id];
          if (from && to) connect(from.block, to.block);
        });
      });
      Object.values(graph.sources).forEach((source) => {
        const from = nodeById["file:" + source.artifact.id];
        source.to.forEach((stepId) => {
          const to = nodeById[stepId];
          if (from && to) connect(from.block, to.block);
        });
      });

      function gap(left, right) {
        return (left.width + right.width) / 2 + M.COL_GAP;
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

      // Relax. A block may move only inside the room its neighbors leave, so the
      // arrangement stays valid; alternating the sweep direction keeps the result
      // from leaning the way it was traversed.
      for (let pass = 0; pass < 24; pass += 1) {
        const order = pass % 2 ? blocks.slice().reverse() : blocks;
        order.forEach((block) => {
          if (!block.near.length) return;
          let low = block.width / 2;
          let high = Infinity;
          block.layers.forEach((layer) => {
            const list = perLayer[layer];
            const index = list.indexOf(block);
            const before = list[index - 1];
            const after = list[index + 1];
            if (before) low = Math.max(low, before.cx + gap(before, block));
            if (after) high = Math.min(high, after.cx - gap(block, after));
          });
          const target =
            block.near.reduce((sum, other) => {
              return sum + other.cx;
            }, 0) / block.near.length;
          block.cx = Math.min(Math.max(target, low), Math.max(low, high));
        });
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
        block.layers.forEach((layer) => {
          const list = block.byLayer[layer];
          const total =
            list.reduce((sum, node) => {
              return sum + node.w;
            }, 0) +
            M.COL_GAP * (list.length - 1);
          let x = block.cx - total / 2;
          list.forEach((node) => {
            node.px = x;
            x += node.w + M.COL_GAP;
          });
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
          h: nodeHeight(step),
          order: step._order,
        });
      });
      Object.entries(graph.sources).forEach((entry) => {
        rowFor(entry[1].layer).push({
          type: "artifact",
          id: "file:" + entry[0],
          artifact: entry[1].artifact,
          to: entry[1].to,
          w: M.ART_W,
          h: M.ART_H,
          order: -1,
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
            const upstream =
              node.type === "step"
                ? (graph.parents[node.id] || []).map((edge) => {
                    return indexOf[edge.from];
                  })
                : node.to.map((id) => {
                    return indexOf[id];
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
            indirect: edge.indirect,
            file: false,
          });
        });
      });
      Object.values(graph.sources).forEach((source) => {
        source.to.forEach((stepId) => {
          const from = byId["file:" + source.artifact.id];
          if (!from || !byId[stepId]) return;
          edges.push({
            from: from,
            to: byId[stepId],
            data: source.artifact.label,
            indirect: false,
            file: true,
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

    /* Compact drops the label, not the band. A group's name needs more width
       than a compact node has, and set small enough to fit it would be a smear
       across the top of the band; the band itself still shows that those steps
       are one concern, and its tooltip still names it. */
    function drawBandLabels(root, bands) {
      if (compact) return;
      bands.forEach((band) => {
        const text = truncateLabel(band.group.label, 30);
        root.appendChild(
          svg("rect", {
            class: "band-label-bg",
            x: band.x0 + 7,
            y: band.y0 + 2,
            width: text.length * 6 + 12,
            height: 15,
            rx: 3,
          })
        );
        const label = svg("text", {
          class: "band-label",
          x: band.x0 + 13,
          y: band.y0 + 13,
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
        const ends = [edge.from.step, edge.to.step].filter(Boolean);
        const dim = !ends.some(matchesQuery);
        const path = svg("path", {
          class:
            "edge" +
            (edge.file ? " edge-file" : "") +
            (edge.indirect ? " edge-indirect" : "") +
            (active ? " active" : "") +
            (dim && !active ? " dim" : ""),
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
            class:
              "edge-arrow" +
              (active ? " active" : "") +
              (dim && !active ? " dim" : ""),
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

      // Labels only for the selected step's edges: naming every flow at once
      // turns the chart into a wall of 9px type.
      edges.filter(edgeActive).forEach((edge) => {
        if (!edge.data) return;
        const midX =
          edge.channel === undefined ? (edge.x1 + edge.x2) / 2 : edge.channel;
        const midY = (edge.y1 + edge.y2) / 2;
        const text = truncateLabel(edge.data, 44);
        const box = svg("rect", {
          class: "edge-label-bg",
          x: midX - text.length * 2.5 - 5,
          y: midY - 8,
          width: text.length * 5 + 10,
          height: 15,
          rx: 4,
        });
        root.appendChild(box);
        const label = svg("text", {
          class: "edge-label",
          x: midX,
          y: midY + 3,
          "text-anchor": "middle",
        });
        label.textContent = text;
        root.appendChild(label);
      });
    }

    function drawArtifactNode(root, node) {
      const group = svg("g", {
        class: "artifact source",
        transform: "translate(" + node.x + "," + node.y + ")",
      });
      group.appendChild(svg("rect", { width: node.w, height: node.h }));
      const concept = conceptOf(node.artifact);
      const family = artifactConceptLine(node.artifact);
      const mark = concept
        ? sceneGlyph(concept.path, 9, family ? 6 : 13, 14)
        : null;
      if (mark) group.appendChild(mark);
      const indent = mark ? 29 : 10;
      const label = svg("text", { x: indent, y: family ? 16 : 23 });
      label.textContent = truncateLabel(node.artifact.label, 28);
      group.appendChild(label);
      if (family) {
        const line = svg("text", { x: indent, y: 29, class: "sub" });
        line.setAttribute("font-size", "9.5");
        line.setAttribute("fill", "var(--muted)");
        line.textContent = truncateLabel(family, 30);
        group.appendChild(line);
      }
      const tip = svg("title");
      tip.textContent =
        node.artifact.label +
        (concept ? " — " + concept.label : "") +
        "\n" +
        node.artifact.note +
        "\nProduced by the other pipeline; read here.";
      group.appendChild(tip);
      root.appendChild(group);
    }

    function drawNode(root, node) {
      const step = node.step;
      const dim = !matchesQuery(step);
      const group = svg("g", {
        class:
          "node" +
          (dim ? " dim" : "") +
          (state.selected === step.id ? " selected" : ""),
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

      /* A reduced node carries the step's name, wrapped, and at mid the one
         line that says what kind of step it is and which model it calls.

         Compact stops at the name deliberately. The script, the kind and the
         model are one line of small type each, and three of those in a
         104-unit box is a grey block rather than a label. What is
         left out of either is still on the node—in its tooltip and its
         accessible name—and set out in full in the drawer and the modal. */
      if (reduced) {
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
          const facts = [DATA.kinds[step.kind].label];
          if (step.calls_per_run && step.calls_per_run !== "1")
            facts.push("×N");
          if (step.model) facts.push(step.model.split(" (")[0]);
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
        return;
      }

      const title = svg("text", { class: "title", x: 16, y: 22 });
      title.textContent = truncateLabel(step.label, 33);
      group.appendChild(title);

      const sub = svg("text", { class: "sub", x: 16, y: 38 });
      sub.textContent = truncateLabel(step.script.replace(".py", ""), 32);
      group.appendChild(sub);

      const facts = [];
      facts.push(DATA.kinds[step.kind].label);
      if (step.lane === "shared") facts.push("shared");
      if (step.calls_per_run && step.calls_per_run !== "1") facts.push("×N");
      // Bare model id only—where it was resolved from belongs in the drawer.
      if (step.model) facts.push(truncateLabel(step.model.split(" (")[0], 18));
      const factLine = svg("text", { class: "metric", x: 16, y: 55 });
      factLine.textContent = truncateLabel(facts.join(" · "), 40);
      group.appendChild(factLine);

      // What the step writes belongs to the step, not beside it: this is where
      // the pipeline's state actually changes. Each line carries the glyph of
      // the concept it advances, so a branch can be followed by its mark alone.
      const written = state.showArtifacts ? step.outputs || [] : [];
      written.forEach((artifactId, index) => {
        const artifact = artifactById[artifactId];
        if (!artifact) return;
        const concept = conceptOf(artifact);
        const rowY = M.NODE_H + index * M.FILE_H;
        const row = svg("g", { class: "writes" });
        row.appendChild(
          svg("path", {
            class: "writes-rule",
            d: "M12 " + (rowY - 6) + " L" + (node.w - 12) + " " + (rowY - 6),
          })
        );
        const mark = concept
          ? sceneGlyph(concept.path, 16, rowY - 5, 12)
          : null;
        if (mark) row.appendChild(mark);
        const text = svg("text", { x: mark ? 33 : 16, y: rowY + 5 });
        text.textContent = "writes  " + truncateLabel(artifact.label, 30);
        row.appendChild(text);
        const tip = svg("title");
        tip.textContent =
          artifact.label +
          (concept ? " — " + concept.label : "") +
          "\n" +
          artifact.note;
        row.appendChild(tip);
        group.appendChild(row);
      });

      bindNode(group, step);
      root.appendChild(group);
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
       it away. The full chart is not sized here: it is drawn at its natural
       size and scrolled, which is why it is the one that stops fitting. */
    function refit() {
      if (!reduced || !naturalSize) return;
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
      // The full chart is drawn at its natural size and scrolled sideways when
      // the column is too narrow for it. The compact one must never scroll—that
      // is the whole point of it—so it is given no minimum and the stylesheet
      // fits it to the column.
      host.style.minWidth = reduced ? "" : geometry.width + "px";
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
        if (node.type === "artifact") drawArtifactNode(host, node);
      });
      geometry.nodes.forEach((node) => {
        if (node.type === "step") drawNode(host, node);
      });
      drawBandLabels(host, geometry.bands);

      const stepNodes = geometry.nodes.filter((node) => {
        return node.type === "step";
      });
      const visible = stepNodes.filter((node) => {
        return matchesQuery(node.step);
      }).length;
      hint.textContent = state.query
        ? visible +
          " of " +
          stepNodes.length +
          " visible steps match “" +
          state.query +
          "”"
        : "Click any step for its prompt, output schema and dependencies. " +
          "Hovering a shaded band names its concern; selecting a step labels " +
          "its arrows with the data that travels along them.";

      /* What the figure is, and then the marks that carry no label of their
         own. The layer semantics, the branch structure and what a step node
         prints belong to the prose and to the drawing itself, and a caption
         that repeated them argued with both. A mark is named only when it is
         actually drawn.

         Each caption describes the drawing it is under. Naming the artifact
         lines and the script under a figure that has neither would be
         describing another version of itself, so a reduced caption says
         instead that it is reduced and where the rest is. */
      const sourceCount = geometry.nodes.length - stepNodes.length;
      const bands = geometry.bands.length;
      const marks = reduced
        ? [
            compact ? "The color bar gives the step kind." : "",
            "The drawing is reduced to fit the column; the full chart adds " +
              "the detail it leaves out.",
          ]
        : [
            sourceCount
              ? "Gray boxes are data the other pipeline produces."
              : "",
            bands ? "A shaded band gathers the steps of one concern." : "",
          ];

      fillCaption(
        captionNode,
        "Figure",
        figureNumber,
        [DATA.lanes[state.tab].label + " pipeline as a dependency graph."]
          .concat(marks.filter(Boolean))
          .join(" ")
      );
    }

    /* ------------------------------------------------------------- mount */

    function select(stepId) {
      state.selected = stepId;
      openDrawer(stepById[stepId], instance);
      draw();
    }

    search.addEventListener("input", () => {
      state.query = search.value.trim().toLowerCase();
      draw();
    });

    /* Measuring only: the caller wants to know how much room this pipeline's
       full drawing needs, and no chart is mounted. The layout is arithmetic over
       the spec—no text is measured, nothing is appended—so asking is cheap, and
       it is the only honest way to decide whether the full chart fits. */
    if (settings.measure) {
      const geometry = layout();
      return { width: geometry.width, height: geometry.height };
    }

    // Only what the prose above cannot say for itself: the entry point and the
    // size of the graph. The lane's own blurb is deliberately not repeated here
    //—the authored section introduces the pipeline, and saying it twice made
    // the figure look like it was arguing with the text.
    const lede = el("p", { class: "lane-lede" }, [
      el("span", { text: "Entry point " }),
      el("code", { class: "entry", text: lane.entry }),
    ]);

    /* The way to the full-screen chart. It is offered in both versions, for the
       same reason in each: the graph is wider than what it is drawn into. On a
       phone that is the compact figure's missing detail; in the report's text
       column it is the right-hand third of a chart that has to be scrolled to
       be seen at all. */
    function expandButton() {
      return el("button", {
        class: "expand",
        type: "button",
        text: reduced ? "Open the full chart" : "Full screen",
        title:
          "Open " +
          lane.label +
          " pipeline as a full-screen chart, with the toolbar and every detail.",
        onclick: function () {
          openChartModal(laneId, figureNumber);
        },
      });
    }

    host.appendChild(lede);
    if (reduced) {
      // No toolbar: a search field and six filter toggles cost more height than
      // the figure they filter, and filtering a chart this reduced answers
      // nothing that opening the full one does not answer better.
      if (settings.expandable) {
        host.appendChild(
          el("div", { class: "chart-actions" }, [expandButton()])
        );
      }
    } else {
      const toolbar = el("div", { class: "toolbar" }, [search, filters]);
      if (settings.expandable) toolbar.appendChild(expandButton());
      host.appendChild(toolbar);
      host.appendChild(hint);
      renderToolbar();
    }
    host.appendChild(
      el("figure", { class: "figure" }, [
        captionNode,
        el("div", { class: "chart-scroll" }, [flow]),
      ])
    );

    draw();

    instance.clearSelection = function () {
      if (state.selected === null) return;
      state.selected = null;
      draw();
    };
    // Re-fitting is not re-drawing: the layout is unchanged, only the size the
    // finished drawing is rendered at, so a resize costs one style write.
    instance.refit = refit;
    // A chart can be replaced—the page crossing into the compact size, or the
    // modal closing—and a dead instance left in `charts` would go on drawing
    // into a detached node every time the drawer cleared the other selection.
    instance.destroy = function () {
      const index = charts.indexOf(instance);
      if (index !== -1) charts.splice(index, 1);
      clear(host);
    };
    charts.push(instance);
    return instance;
  }

  /* ------------------------------------------------------------- drawer */

  function promptHtml(prompt) {
    return (prompt.segments || [])
      .map((segment) => {
        const conditions = (segment.conditions || []).length
          ? '<span class="cond">' +
            escapeHtml(segment.conditions.join("  ·  ")) +
            "</span>"
          : "";
        const body = escapeHtml(segment.text)
          .replace(/&lt;&lt;([a-z_]+)&gt;&gt;/g, '<span class="role">$1</span>')
          .replace(/\{[^{}\n]{1,80}\}/g, (match) => {
            return '<span class="ph">' + match + "</span>";
          });
        return conditions + body;
      })
      .join("");
  }

  function schemaBlock(name) {
    const schema = DATA.schemas[name];
    if (!schema) return null;
    const inner = el("div", { class: "inner" });
    if (schema.docstring) {
      inner.appendChild(el("p", { class: "sub", text: schema.docstring }));
    }
    (schema.fields || []).forEach((field) => {
      inner.appendChild(
        el("div", { class: "schema-field" }, [
          el("span", { class: "fname", text: field.name }),
          el("span", { text: "  " }),
          el("span", { class: "ftype", text: field.annotation }),
          field.description
            ? el("div", { class: "fdesc", text: field.description })
            : null,
        ])
      );
    });
    return el("details", { class: "block" }, [
      el("summary", {
        text: name + "—" + (schema.fields || []).length + " fields",
      }),
      inner,
    ]);
  }

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

  function dependentList(step) {
    return DATA.steps
      .filter((other) => {
        return (other.depends_on || []).some((dep) => {
          return dep.on === step.id;
        });
      })
      .map((other) => {
        const dep = other.depends_on.filter((entry) => {
          return entry.on === step.id;
        })[0];
        return "<b>" + escapeHtml(other.label) + "</b>—" + escapeHtml(dep.data);
      })
      .join("<br>");
  }

  /* Everything a step can be asked about, written into `body`.
     Two readers call this. The drawer summons it for one step at a time, and
     the print appendix lays the same material out for every step, because paper
     cannot be clicked. `expand` is what that second reader needs: the prompt
     tabs become every prompt in sequence, since a printed page has no "show the
     rest" affordance. */
  function stepDetail(body, step, expand) {
    const summary = step.summary || {};
    body.appendChild(el("h3", { text: "What this step does" }));
    body.appendChild(
      el("p", { text: summary.what_it_does || step.spec_summary })
    );
    if (summary.why_this_design) {
      body.appendChild(el("h3", { text: "Why it is built this way" }));
      body.appendChild(el("p", { text: summary.why_this_design }));
    }
    if ((summary.constraints || []).length) {
      body.appendChild(el("h3", { text: "Rules it enforces" }));
      const list = el("ul", { class: "bullets" });
      summary.constraints.forEach((item) => {
        list.appendChild(el("li", { text: item }));
      });
      body.appendChild(list);
    }

    body.appendChild(el("h3", { text: "Facts from the source" }));
    const table = el("table", { class: "facts" });
    const rows = [
      factRow(
        "Source",
        "<code>" +
          escapeHtml(step.script) +
          (step.line ? ":" + step.line : "") +
          "</code> → <code>" +
          escapeHtml(step.function) +
          "()</code>"
      ),
      factRow("Kind", escapeHtml(DATA.kinds[step.kind].label)),
      factRow("Pipeline", escapeHtml(DATA.lanes[step.lane].label)),
      factRow(
        "Part of",
        step.group && groupById[step.group]
          ? escapeHtml(groupById[step.group].label) +
              (groupById[step.group].note
                ? "<span class='sub'>—" +
                  escapeHtml(groupById[step.group].note) +
                  "</span>"
                : "")
          : null
      ),
      factRow("Phase", step.phase ? escapeHtml(step.phase) : null),
      factRow(
        "Needs",
        dependencyList(step) || "Nothing—this step starts a branch"
      ),
      factRow("Feeds", dependentList(step) || null),
      factRow(
        "Model",
        step.model
          ? "<code>" +
              escapeHtml(step.model) +
              "</code>" +
              (step.model_source && step.model_source !== "call site"
                ? " <span class='sub'>(from " +
                  escapeHtml(step.model_source) +
                  ")</span>"
                : "")
          : null
      ),
      factRow(
        "Reasoning effort",
        step.effort ? "<code>" + escapeHtml(step.effort) + "</code>" : null
      ),
      factRow("Calls per run", escapeHtml(step.calls_per_run)),
      factRow(
        "Output schema",
        (step.schemas || []).length
          ? step.schemas
              .map((name) => {
                return "<code>" + escapeHtml(name) + "</code>";
              })
              .join(", ")
          : null
      ),
      factRow(
        "Opt out with",
        step.skip_flag
          ? "<code>" + escapeHtml(step.skip_flag) + "</code>"
          : null
      ),
      factRow("Note", step.model_note ? escapeHtml(step.model_note) : null),
      factRow("Reads", artifactList(step.inputs) || null),
      factRow("Writes", artifactList(step.outputs) || null),
    ];
    rows.forEach((row) => {
      if (row) table.appendChild(row);
    });
    body.appendChild(table);

    if ((step.schemas || []).length) {
      body.appendChild(el("h3", { text: "Structured output" }));
      step.schemas.forEach((name) => {
        const block = schemaBlock(name);
        if (block) body.appendChild(block);
      });
    }

    if ((step.prompts || []).length) {
      body.appendChild(el("h3", { text: "Prompt template" }));
      body.appendChild(
        el("p", {
          class: "sub",
          html:
            "Literal instruction text extracted from the source. " +
            "<span class='ph'>{highlighted}</span> marks where runtime data is injected; " +
            "gray lines above a block are the conditions that guard it.",
        })
      );
      if (expand) {
        step.prompts.forEach((prompt) => {
          body.appendChild(
            el("p", { class: "prompt-name", text: prompt.symbol })
          );
          body.appendChild(
            el("pre", { class: "prompt", html: promptHtml(prompt) })
          );
        });
      } else {
        const tabs = el("div", { class: "tabs" });
        const panel = el("div", {});
        step.prompts.forEach((prompt, index) => {
          const tab = el("button", {
            class: "tab",
            type: "button",
            "aria-selected": index === 0 ? "true" : "false",
            text: prompt.symbol,
            onclick: function () {
              Array.prototype.forEach.call(tabs.children, (child) => {
                child.setAttribute("aria-selected", "false");
              });
              tab.setAttribute("aria-selected", "true");
              panel.innerHTML =
                "<pre class='prompt'>" + promptHtml(prompt) + "</pre>";
            },
          });
          tabs.appendChild(tab);
        });
        body.appendChild(tabs);
        panel.innerHTML =
          "<pre class='prompt'>" + promptHtml(step.prompts[0]) + "</pre>";
        body.appendChild(panel);
      }
    }
  }

  function renderDrawer(step) {
    const head = document.getElementById("drawer-title");
    head.textContent = step.label;
    const body = document.getElementById("drawer-body");
    clear(body);
    stepDetail(body, step, false);
    body.scrollTop = 0;
  }

  /* The drawer is one panel shared by both charts, because two open at once
     would ask the reader which half of the page they are looking at. `owner` is
     the chart that raised it; every other chart drops its selection so only one
     node on the page is ever highlighted. */
  function openDrawer(step, owner) {
    charts.forEach((chart) => {
      if (chart !== owner) chart.clearSelection();
    });
    renderDrawer(step);
    document.getElementById("drawer").classList.add("open");
  }

  function closeDrawer() {
    document.getElementById("drawer").classList.remove("open");
    charts.forEach((chart) => {
      chart.clearSelection();
    });
  }

  /* ---------------------------------------------------------- chart modal */

  /* The full chart, over the whole viewport, on demand.

     A column too narrow for the full chart gets a reduced figure inline, and
     this is where the detail it gave up is kept: the chart at full size, with
     its toolbar,
     its search and its artifact lines, scrollable in both directions because a
     dependency graph is simply wider than a phone. It is built when it is
     opened and torn down when it is closed—the report already draws two charts
     on load, and a third held in reserve behind every figure would be paid for
     by every reader whether or not they ever pressed the button. */
  const modalState = { chart: null, opener: null };

  function chartModal() {
    return document.getElementById("chart-modal");
  }

  function openChartModal(laneId, figureNumber) {
    const modal = chartModal();
    const mount = document.getElementById("chart-modal-body");
    closeChartModal(); // never two charts of the same lane at once
    modalState.opener = document.activeElement;
    document.getElementById("chart-modal-title").textContent =
      "Figure " + figureNumber + "—" + laneLabel(laneId) + " pipeline";
    // Shown before it is filled: a chart built inside a `display:none` panel
    // measures every string and every scroll extent as zero.
    modal.classList.add("open");
    modal.removeAttribute("aria-hidden");
    modalState.chart = createChart(mount, laneId, figureNumber, {
      size: "full",
    });
    // Opened at the left edge, a chart wider than the panel shows its empty
    // margin channel and nothing else. Start in the middle, where the graph is.
    const scroller = mount.querySelector(".chart-scroll");
    if (scroller) {
      scroller.scrollLeft = (scroller.scrollWidth - scroller.clientWidth) / 2;
    }
    // The page behind must not scroll under the overlay; on a phone it is the
    // difference between closing the modal and losing your place in the report.
    document.body.classList.add("modal-open");
    document.getElementById("chart-modal-close").focus();
  }

  function closeChartModal() {
    const modal = chartModal();
    if (modalState.chart) {
      modalState.chart.destroy();
      modalState.chart = null;
    }
    if (!modal.classList.contains("open")) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
    if (modalState.opener && modalState.opener.focus) modalState.opener.focus();
    modalState.opener = null;
  }

  function chartModalIsOpen() {
    return chartModal().classList.contains("open");
  }

  /* ------------------------------------------------- shared computed parts */

  function stepsOf(laneId) {
    return DATA.steps.filter((step) => {
      return step.column === laneId;
    });
  }

  /* The room the widest pipeline's full drawing needs, in CSS pixels—the full
     chart is drawn one user unit to the pixel, so its layout size is the space
     it asks the page for.

     Measured from the spec rather than written down, so adding a step that
     widens a layer moves the point at which the figures go compact, with
     nothing to remember to update. Measured once: it depends on the data, not
     on the window, so a resize never recomputes it. */
  /* The factor a reduced drawing is rendered at, in a column this wide.

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

  function laneLabel(laneId) {
    const lane = DATA.lanes[laneId];
    return lane ? lane.label : laneId;
  }

  function factOf(key) {
    return (DATA.facts && DATA.facts[key]) || null;
  }

  /* A numbered caption. Figures and tables are numbered in Python, in document
     order, so the number a component prints is the one the prose cites—a
     caption can never drift out of step with a cross-reference.

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

     Every caption on the page is built here, whichever element carries it: a
     figure's is a `<figcaption>` inside its `<figure>` and a table's is a
     block above the table. */
  function caption(kind, number, text) {
    return fillCaption(el("p", {}), kind, number, text);
  }

  function figureCaption(kind, number, text) {
    return fillCaption(el("figcaption", {}), kind, number, text);
  }

  /* Rewritable, because a chart redraws its own caption whenever the filters
     change what is on the canvas. */
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

  function dataTable(headers, rows) {
    const table = el("table", { class: "data" });
    table.appendChild(
      el(
        "tr",
        {},
        headers.map((header) => {
          return el("th", { text: header });
        })
      )
    );
    rows.forEach((row) => {
      table.appendChild(el("tr", {}, row));
    });
    return tableScroll(table);
  }

  function code(text) {
    return el("code", { text: text });
  }

  function plain(text) {
    return el("td", { text: text === null || text === undefined ? "—" : text });
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

  function arrowHead(host, x, y, direction) {
    const size = 4;
    const tip =
      direction === "left" ? x - size : direction === "right" ? x + size : x;
    const points =
      direction === "down"
        ? [x, y + size, x - size + 1, y - 1, x + size - 1, y - 1]
        : [tip, y, x, y - size + 1, x, y + size - 1];
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

    /* The four step kinds, laid out by the width each label actually needs and
       wrapped when the box runs out—equal cells fit the shortest name and
       clipped the longest. */
    kinds: function (host, part) {
      let x = part.x;
      let y = part.y + 12;
      Object.keys(DATA.kinds).forEach((kind) => {
        const width = DATA.kinds[kind].label.length * 6.6 + 26;
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

    prose: function (host, part) {
      const x = part.x + 16;
      const width = part.w - 32;
      [0.92, 1, 0.95, 1, 0.66].forEach((share, index) => {
        host.appendChild(
          sRect(x, part.y + 46 + index * 13, width * share, 4, "tbar")
        );
      });
    },

    timeline: function (host, part) {
      const x = part.x + 16;
      const width = part.w - 32;
      const y = part.y + 78;
      const bands = [0, 0.34, 0.62];
      const spans = [0.34, 0.28, 0.38];
      bands.forEach((start, index) => {
        host.appendChild(
          sRect(
            x + width * start,
            y - 22,
            width * spans[index] - 3,
            18,
            "tband"
          )
        );
      });
      host.appendChild(sPath("M" + x + " " + y + "h" + width, "trule"));
      [0.04, 0.14, 0.26, 0.38, 0.47, 0.61, 0.7, 0.86, 0.95].forEach(
        (at, index) => {
          host.appendChild(
            svg("circle", {
              cx: x + width * at,
              cy: y,
              r: index === 4 ? 4 : 2.4,
              class: index === 4 ? "tdot on" : "tdot",
            })
          );
        }
      );
    },

    map: function (host, part) {
      const x = part.x + 16;
      const y = part.y + 42;
      const width = part.w - 32;
      const height = 62;
      host.appendChild(sRect(x, y, width, height, "tplate"));
      // The coastline is drawn for a 224-unit plate and scaled to whatever
      // width the box has, so the box can be resized without redrawing it.
      const coast = svg("g", {
        transform:
          "translate(" + x + "," + (y + 46) + ") scale(" + width / 224 + ",1)",
      });
      coast.appendChild(
        sPath("M0 0q24 -9 46 -3t44 -10 42 2 40 -11 52 -1", "tcoast")
      );
      host.appendChild(coast);
      [
        [0.22, 0.34],
        [0.44, 0.62],
        [0.62, 0.28],
        [0.8, 0.55],
      ].forEach((at, index) => {
        const px = x + width * at[0];
        const py = y + height * at[1];
        host.appendChild(
          sPath(
            "M" + px + " " + py + "l-4 -7a4.6 4.6 0 1 1 8 0Z",
            index === 1 ? "tpin on" : "tpin"
          )
        );
      });
    },

    graph: function (host, part) {
      const x = part.x + 16;
      const y = part.y + 40;
      const nodes = [
        [0.5, 0.5, 7],
        [0.18, 0.24, 4],
        [0.24, 0.78, 4],
        [0.52, 0.12, 3.4],
        [0.78, 0.3, 4],
        [0.84, 0.74, 3.4],
        [0.46, 0.9, 3.4],
      ];
      const width = part.w - 32;
      const height = 66;
      const at = (node) => {
        return [x + width * node[0], y + height * node[1]];
      };
      [
        [0, 1],
        [0, 2],
        [0, 3],
        [0, 4],
        [0, 6],
        [1, 2],
        [4, 5],
        [2, 6],
      ].forEach((edge) => {
        const a = at(nodes[edge[0]]);
        const b = at(nodes[edge[1]]);
        host.appendChild(
          sPath("M" + a[0] + " " + a[1] + "L" + b[0] + " " + b[1], "tlink")
        );
      });
      nodes.forEach((node, index) => {
        const point = at(node);
        host.appendChild(
          svg("circle", {
            cx: point[0],
            cy: point[1],
            r: node[2],
            class: index === 0 ? "tnode on" : "tnode",
          })
        );
      });
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
        "it, and along the foot the four encodings every story is read through.",
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
      document.querySelectorAll(".figref"),
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

    document.addEventListener("click", (event) => {
      const ref = event.target.closest ? event.target.closest(".figref") : null;
      if (!ref) return;
      event.preventDefault();
      const partId = ref.getAttribute("data-part");
      if (teaserState.pinned && teaserState.part === partId) clearTeaserFocus();
      else setTeaserFocus(partId, { pinned: true, fromRef: true });
    });

    document.addEventListener("focusin", (event) => {
      const ref = event.target.closest ? event.target.closest(".figref") : null;
      if (!ref || teaserState.pinned) return;
      setTeaserFocus(ref.getAttribute("data-part"), { fromRef: true });
    });

    if (!canHover) return;

    document.addEventListener("mouseover", (event) => {
      const ref = event.target.closest ? event.target.closest(".figref") : null;
      if (!ref || teaserState.pinned) return;
      window.clearTimeout(teaserState.hoverTimer);
      teaserState.hoverTimer = window.setTimeout(() => {
        setTeaserFocus(ref.getAttribute("data-part"), { fromRef: true });
      }, HOVER_DELAY);
    });

    document.addEventListener("mouseout", (event) => {
      const ref = event.target.closest ? event.target.closest(".figref") : null;
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

  /* --------------------------------------------------------- components */

  /* Each entry hydrates one `::: name` block from the Markdown. `mount` is the
     empty div the compiler left, `params` are the block's `key=value` arguments,
     and `numbers` are the figure and table numbers Python assigned to it. The
     roster here must match COMPONENTS in `report.py`, which is what makes an
     unknown block a build error rather than a blank space on the page. */
  const COMPONENTS = {
    buildinfo: function (mount) {
      const rows = [
        ["Version", DATA.version || DATA.generated_at],
        ["Built", DATA.generated_at],
        ["Commit", DATA.commit || "—"],
        ["Branch", DATA.branch || "—"],
        ["Report source", (DATA.report && DATA.report.source) || "—"],
      ];
      const list = el("dl", { class: "buildinfo" });
      rows.forEach((row) => {
        list.appendChild(el("dt", { text: row[0] }));
        list.appendChild(el("dd", {}, [code(row[1])]));
      });
      mount.appendChild(list);
    },

    teaser: function (mount, params, numbers) {
      createTeaser(mount, numbers.figure);
    },

    factgrid: function (mount, params) {
      const grid = el("div", { class: "factgrid" });
      (params.keys || "").split(",").forEach((raw) => {
        const key = raw.trim();
        if (!key) return;
        const fact = factOf(key);
        if (!fact) return;
        grid.appendChild(
          el("div", { class: "factcell", title: fact.source }, [
            el("div", { class: "value", text: fact.display }),
            el("div", { class: "label", text: key }),
          ])
        );
      });
      mount.appendChild(grid);
      if (params.caption) {
        mount.appendChild(el("p", { class: "cap", text: params.caption }));
      }
    },

    /* A view of the running application, taken from the position the markdown
       declares. The picture arrives in the payload as a data URI, like every
       other asset on this page, so the report stays one file.

       Under the picture, in small type, is the declaration it was taken
       from—route, viewport, capture date. It is there because this is the one
       figure on the page a reader cannot re-derive by reading the source: the
       line says which position of which build it shows, and names the state a
       reader would have to reach to see it for themselves. */
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
      const provenance = [shot.declaration];
      if (shot.captured)
        provenance.push("captured " + shot.captured.slice(0, 10));
      if (shot.status !== "current") {
        provenance.push("the declaration has changed since—retake it");
      }
      mount.appendChild(
        el("figure", { class: "figure shot" }, [
          figureCaption("Figure", numbers.figure, shot.caption),
          el("div", { class: "shot-frame" }, [
            el("img", {
              class: "shot-img",
              src: shot.src,
              alt: shot.alt || shot.caption,
              // The intrinsic size in CSS pixels, so the page reserves the
              // right box before the picture decodes—and so no lazy loading is
              // needed, which on paper would risk printing an undecoded image.
              width: shot.width,
              height: shot.height,
            }),
          ]),
          el("p", { class: "shot-meta", text: provenance.join("  ·  ") }),
        ])
      );
    },

    /* The figure follows the space it is given: the largest drawing the column
       can actually hold. The full chart needs 990 units and the report's column
       is that wide only past about 1366px of viewport; the mid drawing needs
       660, which is most windows; below that the compact one, scaled to fit.

       A measurement, not a breakpoint, because a breakpoint is a guess at this
       number and goes stale the moment a step is added to the spec.

       Width alone chooses between the full chart and a reduced one, since the
       full chart is drawn at its natural size and scrolls—it is a good deal
       taller than any viewport, so a height test would refuse it always. Among
       the reduced sizes height does decide, because they scale: a mid drawing
       squeezed to 0.72 of itself by a short window carries more than the
       compact one and reads worse, so the compact one is used instead.

       Both figures answer together. The prose promises them "at the same scale,
       so that the pipelines may be compared directly", and a page that drew one
       full and the other reduced would quietly break that comparison. */
    pipeline: function (mount, params, numbers) {
      let chart = null;
      let showing = null;

      function sizeFor() {
        const available = mount.clientWidth;
        // Before layout there is no width to measure; nothing is decided on a
        // zero, and the resize pass below settles it once there is a page.
        if (available <= 0) return "full";
        // The full chart is drawn one unit to the pixel and scrolls; either the
        // column holds it or it does not.
        if (widestPipeline("full").width <= available) return "full";

        /* The reduced sizes all scale to the room, so the winner is not the one
           that carries the most but the one that still sets its names largest
           once fitted—and ties go to the one carrying more. It is a real
           question, not a formality: in a 980-unit column 768px tall, mid comes
           out at 9.3px type and compact at 9.5px, so mid wins on a tie; give
           the same column a 900px window and compact grows to 11.2px while mid
           is still held at 10.9px by the same height, and compact takes it. */
        const options = SIZES.filter((name) => name !== "full").map((name) => {
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
          expandable: true,
        });
      }

      sync();
      onViewportChange(sync);
    },

    steptable: function (mount, params, numbers) {
      const steps = stepsOf(params.lane);
      mount.appendChild(
        caption(
          "Table",
          numbers.table,
          "Every documented step of the " +
            laneLabel(params.lane).toLowerCase() +
            " pipeline"
        )
      );
      mount.appendChild(
        dataTable(
          ["Step", "Kind", "Script", "Model", "Effort", "Output schema"],
          steps.map((step) => {
            return [
              el("td", {}, [
                el("span", {
                  class: "swatch",
                  style: "background:" + kindColor(step.kind),
                }),
                el("span", { text: step.label }),
              ]),
              plain(DATA.kinds[step.kind].label),
              el("td", {}, [code(step.script.split("/").slice(-1)[0])]),
              plain(step.model || "—"),
              plain(step.effort || "—"),
              el("td", {}, [
                step.schemas.length
                  ? code(step.schemas.join(", "))
                  : el("span", { text: "—" }),
              ]),
            ];
          })
        )
      );
    },

    /* The vocabulary itself, once, where the report first uses it, split at the
       line the data model turns on: what arrives from outside, and what the
       pipelines make of it. */
    conceptlegend: function (mount) {
      [
        { role: "input", label: "Input" },
        { role: "derived", label: "Output" },
      ].forEach((group) => {
        const members = (DATA.concepts || []).filter((concept) => {
          return concept.role === group.role;
        });
        if (!members.length) return;
        mount.appendChild(
          el("p", { class: "conceptgroup", text: group.label })
        );
        const list = el("dl", { class: "conceptlist" });
        members.forEach((concept) => {
          list.appendChild(
            el("dt", {}, [
              glyph(concept.path, "glyph big"),
              el("span", { text: concept.label }),
            ])
          );
          list.appendChild(el("dd", { text: concept.blurb }));
        });
        mount.appendChild(list);
      });
    },

    modeltable: function (mount, params, numbers) {
      mount.appendChild(
        caption(
          "Table",
          numbers.table,
          "Every model call site in the generation scripts"
        )
      );
      mount.appendChild(
        dataTable(
          ["Where", "Model", "Resolved from", "Effort", "Schema", "Step"],
          (DATA.call_sites || []).map((site) => {
            return [
              el("td", {}, [
                code(site.script + ":" + site.line),
                el("div", { class: "path", text: site.function + "()" }),
              ]),
              plain(site.model || "—"),
              plain(site.model_source || "—"),
              plain(site.effort || "—"),
              el("td", {}, [
                site.schema ? code(site.schema) : el("span", { text: "—" }),
              ]),
              el("td", {}, [
                site.step
                  ? el("span", {
                      text: (stepById[site.step] || {}).label || site.step,
                    })
                  : el("span", { class: "warn", text: "unclaimed" }),
              ]),
            ];
          })
        )
      );
    },

    cliflags: function (mount, params, numbers) {
      const name = params.script.split("/").slice(-1)[0];
      const entry = (DATA.script_index || {})[name];
      if (!entry) {
        mount.appendChild(
          emptyNote("No script named <code>" + escapeHtml(name) + "</code>.")
        );
        return;
      }
      mount.appendChild(
        caption(
          "Table",
          numbers.table,
          "The " +
            entry.flags.length +
            " command-line options of " +
            entry.script
        )
      );
      mount.appendChild(
        dataTable(
          ["Flag", "Default", "What it does"],
          entry.flags.map((flag) => {
            return [
              el("td", {}, [code(flag.flags.join(", "))]),
              plain(
                flag.default && flag.default !== "None" ? flag.default : "—"
              ),
              plain(flag.help || ""),
            ];
          })
        )
      );
    },

    schemalist: function (mount, params) {
      const names = (params.names || "")
        .split(",")
        .map((name) => {
          return name.trim();
        })
        .filter(Boolean);
      const wanted = names.length ? names : Object.keys(DATA.schemas).sort();
      wanted.forEach((name) => {
        const block = schemaBlock(name);
        if (block) mount.appendChild(block);
      });
    },

    kindlegend: function (mount) {
      const list = el("dl", { class: "kindlist" });
      Object.entries(DATA.kinds).forEach((entry) => {
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

    coverage: function (mount) {
      const sites = DATA.call_sites || [];
      const unclaimed = sites.filter((site) => {
        return !site.step;
      });
      mount.appendChild(
        el("p", { class: "cap" }, [
          el("span", {
            text:
              sites.length -
              unclaimed.length +
              " of " +
              sites.length +
              " model call sites are claimed by a documented step. ",
          }),
          el("span", {
            text: unclaimed.length
              ? "The build treats the rest as an error, so this page should " +
                "never show any."
              : "An unclaimed call site fails the build, which is why this " +
                "number is complete rather than merely large.",
          }),
        ])
      );
    },
  };

  /* ----------------------------------------------------- print appendix */

  /* On screen, a step's prompt, schema and dependencies are one click away in
     the drawer. Paper has no click, so a printed report that stopped at the
     figures would be missing the material the figures are an index to. This
     builds that material as an appendix: every step, in the order the pipelines
     run them, with the drawer's own content expanded.

     It is print-only. On screen it would double the length of the page to say
     what the drawer already says on demand, so the stylesheet hides it and the
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

  /* The compiled contents list is built in Python from the authored headings,
     which the appendix is not one of. Adding the entry here—print-only, like
     the section it points at—keeps the printed contents a description of the
     printed document rather than of the Markdown. */
  function addAppendixToContents() {
    const list = document.querySelector(".toc > .toc-list");
    if (!list) return;
    list.appendChild(
      el("li", { class: "toc-appendix" }, [
        el("a", { href: "#appendix-steps" }, [
          el("span", { class: "toc-no", text: APPENDIX_LETTER }),
          el("span", { text: "Step details" }),
        ]),
      ])
    );
  }

  function renderStepAppendix() {
    const host = document.getElementById("report");
    if (!host || !appendixWanted()) return;

    const columns = Object.keys(DATA.lanes).filter((laneId) => {
      return stepsOf(laneId).length > 0;
    });
    const ordered = columns.reduce((all, laneId) => {
      return all.concat(stepsOf(laneId));
    }, []);
    if (!ordered.length) return;

    const section = el("section", { class: "appendix", id: "appendix-steps" });
    section.appendChild(
      appendixHeading(1, APPENDIX_LETTER, "appendix-steps", "Step details")
    );
    section.appendChild(
      el("p", {
        text:
          "One entry per documented step, in the order the pipelines reach " +
          "them: what the step does, the facts read out of its source, its " +
          "structured output and the literal prompt text it sends. In the " +
          "interactive report this is the panel that opens when a step in " +
          "Figure 2 or Figure 3 is clicked.",
      })
    );

    ordered.forEach((step, index) => {
      const number = APPENDIX_LETTER + "." + (index + 1);
      const slug = "appendix-" + step.id;
      const entry = el("article", { class: "step-detail" });
      entry.appendChild(appendixHeading(2, number, slug, step.label));
      const body = el("div", { class: "step-detail-body" });
      stepDetail(body, step, true);
      entry.appendChild(body);
      section.appendChild(entry);
    });

    host.appendChild(section);
    addAppendixToContents();
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
    // build time answer "which build is this", which is a question for the
    // colophon; the reader at the top of the page is asking "how current is
    // what I am about to read".
    host.appendChild(
      el("span", { class: "chip" }, [
        el("span", {
          text: "Version of " + (DATA.version || DATA.generated_at),
        }),
      ])
    );

    const build = document.getElementById("colophon-build");
    if (build) {
      build.textContent =
        "This rendering was built on " +
        DATA.generated_at +
        " from commit " +
        (DATA.commit || "an unknown revision") +
        " of branch " +
        (DATA.branch || "—") +
        ".";
    }
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

  /* --------------------------------------- notes, principles and citations */

  /* Three kinds of marker are read the same way. An inline note is authored
     once and printed as a numbered list closing its section; a design principle
     is declared once in the introduction and printed as the numbered list every
     `P3` in the prose points into; a citation is numbered by first use and
     printed in the references. All three markers are real links into that
     printed text, so all three work with this file absent and on paper.

     What this adds is the screen reading: the marker opens the text it points
     at in a popover, which keeps an aside—or a principle stated three sections
     earlier, or a reference the reader has no reason to have memorized—off the
     measure until it is asked for. The notes list is withdrawn once that is
     possible; the principles list is the introduction's own content and stays,
     and so does the reference list, which a reader expects to find at the end
     whether or not they ever opened a marker.

     A citation's popover carries the entry's DOI as a live link, so following a
     reference costs the reader neither their place in the sentence nor a trip
     to the back of the document.

     The popover copies the item it points at rather than carrying its own copy
     of the text, so the two renderings cannot drift apart. It is positioned in
     document coordinates, so it stays on its marker while the reader
     scrolls. */
  const POP_REF = ".noteref, .pref, .refref";

  function renderPopovers() {
    const refs = document.querySelectorAll(
      ".report .noteref, .report .pref, .report .refref"
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

  document
    .getElementById("drawer-close")
    .addEventListener("click", closeDrawer);
  document
    .getElementById("chart-modal-close")
    .addEventListener("click", closeChartModal);
  // No click-outside to bind: the panel now covers the whole viewport, so there
  // is no outside. Escape and the close button are the ways back.
  // One Escape, one layer: the drawer opens over the modal, so it closes first
  // and a second press closes the chart behind it.
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    clearTeaserFocus();
    if (document.getElementById("drawer").classList.contains("open")) {
      closeDrawer();
      return;
    }
    if (chartModalIsOpen()) {
      closeChartModal();
      return;
    }
    closeDrawer();
  });

  renderMetaRow();
  hydrate();
  renderStepAppendix();
  renderRail();
  renderTocButton();
  renderPopovers();
  bindPrintDisclosure();

  // The page is fully built. `scripts/export_report_pdf.mjs` waits for this
  // before printing, so a PDF can never catch the report half-hydrated.
  document.documentElement.setAttribute("data-report-ready", "1");
})();
