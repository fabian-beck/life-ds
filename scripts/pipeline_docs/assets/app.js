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
   the other's selection. Colour encodes the step kind and nothing else.

   The chart is a layered DAG, not a sequence. A step's layer is the longest
   path of real data dependencies reaching it, so steps drawn side by side are
   genuinely independent—the map branch and the network branch of the meta
   story really do run without seeing each other. Files a step writes are drawn
   inside its node; files that arrive from the other pipeline become source
   nodes, since nothing in this chart produces them.

   The vertical axis is the dependency graph; the horizontal axis is free, and
   `spec.GROUPS` spends it on meaning. Steps of one concern—plan the image
   searches, run them, match the results—are aligned and banded, so a job that
   takes three layers reads as one vertical strand instead of drifting across the
   chart. Alignment holds only where a group is continuous: a member several
   layers below the rest is placed on its own. Positions are continuous and
   relaxed towards the centre, not slots in a grid. */

(function () {
  "use strict";

  const DATA = window.PIPELINE;
  const SVG_NS = "http://www.w3.org/2000/svg";

  const RAIL_W = 58;
  const NODE_W = 268;
  const NODE_H = 66;
  const FILE_H = 15;
  const ART_W = 214;
  const ART_H = 38;
  const COL_GAP = 26;
  const LAYER_GAP = 52;
  const MARGIN_CH = 26; // side channels for edges that skip a layer
  const PAD = 12;
  const BAND_PAD = 9;
  const BAND_HEAD = 20; // room for a group band's label above its first step
  const HEAD_H = BAND_HEAD + 4; // a band on the first layer has to fit above it

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

  function fmtInt(value) {
    return Number(value || 0).toLocaleString("en-US");
  }

  function fmtSeconds(value) {
    const seconds = Number(value || 0);
    if (seconds >= 90) return (seconds / 60).toFixed(1) + " min";
    return seconds.toFixed(seconds < 10 ? 1 : 0) + " s";
  }

  function fmtTokens(value) {
    const n = Number(value || 0);
    if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
    if (n >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(n);
  }

  function truncateLabel(text, max) {
    return text.length > max ? text.slice(0, max - 1) + "…" : text;
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

  // Artifacts that span several files (the Wikipedia cache, a language folder)
  // have no single filename to print, and naming only the first would be wrong
  // for the steps that write the others.
  function artifactFile(artifact) {
    if (artifact.path.indexOf(",") !== -1) return artifact.label;
    return artifact.path.split("/").slice(-1)[0];
  }

  /* -------------------------------------------------- pipeline chart */

  /* One interactive chart, mounted into `host` and owning its own filter state.

     Everything from here to the end of `createChart` is per-instance: the two
     pipelines are drawn side by side in the document, and a filter applied to
     one must not re-flow the other. The layout itself is unchanged—the layer
     rule, the group blocks and the edge routing are the same code that drew the
     single tabbed chart—it simply closes over an instance `state` and instance
     DOM nodes instead of the page's. */
  function createChart(host, laneId, figureNumber) {
    // Declared up front so `select` can name the instance the drawer belongs to
    // before the instance is finished being built.
    const instance = { lane: laneId };
    const state = {
      tab: laneId,
      kinds: new Set(Object.keys(DATA.kinds)),
      showShared: true,
      showArtifacts: true,
      query: "",
      selected: null,
    };

    const lane = DATA.lanes[laneId];
    const flow = svg("svg", {
      role: "img",
      "aria-label": "Flow chart of the " + lane.label + " pipeline",
    });
    const hint = el("p", { class: "hint" });
    const caption = el("figcaption", {});
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
          "Show the files each step writes, and the files this pipeline reads " +
          "from the other one.",
        text: "Data files",
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
      return NODE_H + (files ? 6 + files * FILE_H : 0);
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
          // Where the barycentre pass put this node in its row, normalized, so a
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
              COL_GAP * (list.length - 1)
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
       are relaxed towards the average position of their graph neighbours, each one
       clamped to the room its neighbours in every layer it occupies actually
       leave. That keeps the arrangement valid at every step while letting sparse
       layers centre themselves under the layers they feed.

       Stage two places the nodes inside each block, centred on it, which is what
       makes a group's steps line up: a run with one step per layer puts every
       step at the same x. */
    function arrange(rows, graph) {
      const blocks = buildBlocks(rows);
      if (!blocks.length) return { blocks: blocks, width: NODE_W };

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
        return (left.width + right.width) / 2 + COL_GAP;
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

      // Relax. A block may move only inside the room its neighbours leave, so the
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
      const origin = PAD + RAIL_W + MARGIN_CH - left;
      blocks.forEach((block) => {
        block.cx += origin;
        // Stage two: the members of one layer, centred on the block.
        block.layers.forEach((layer) => {
          const list = block.byLayer[layer];
          const total =
            list.reduce((sum, node) => {
              return sum + node.w;
            }, 0) +
            COL_GAP * (list.length - 1);
          let x = block.cx - total / 2;
          list.forEach((node) => {
            node.px = x;
            x += node.w + COL_GAP;
          });
        });
      });

      return { blocks: blocks, width: Math.max(NODE_W, right - left) };
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
          x0: block.cx - block.width / 2 - BAND_PAD,
          x1: block.cx + block.width / 2 + BAND_PAD,
          y0: y0 - BAND_HEAD,
          y1: y1 + BAND_PAD,
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
          w: NODE_W,
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
          w: ART_W,
          h: ART_H,
          order: -1,
        });
      });

      // Two barycentre passes: order each row by the average position of its
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
      let y = HEAD_H;
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
        // barycentre order inside a single row; the edge fanning and the channel
        // search below both read rows left to right.
        row.sort((a, b) => {
          return a.x - b.x;
        });
        rails.push({ label: String(index + 1), y0: y, y1: y + rowH });
        y += rowH + LAYER_GAP;
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
        width: PAD * 2 + RAIL_W + MARGIN_CH * 2 + contentW,
        height: (rows.length ? y - LAYER_GAP : HEAD_H) + PAD,
      };
    }

    /* An edge that skips a layer would otherwise be drawn straight through the
       nodes in between. Each one is given a vertical channel—a column of empty
       space free across every layer it crosses—and routed down it. A group's
       band counts as occupied even where its column is empty: a line running
       down the middle of a band would read as belonging to it. */
    function routeLongEdges(edges, rows, contentW, bands) {
      const left = PAD + RAIL_W;
      const right = left + MARGIN_CH * 2 + contentW;
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

    function drawBandLabels(root, bands) {
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
      const x = PAD + RAIL_W - 20;
      rails.forEach((rail) => {
        root.appendChild(
          svg("path", {
            class: "rail-rule",
            d: "M" + x + " " + rail.y0 + " L" + x + " " + rail.y1,
          })
        );
        const label = svg("text", {
          class: "rail-label",
          x: x - 7,
          y: rail.y0 + 13,
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
      const file = artifactFile(node.artifact);
      const single = file !== node.artifact.label;
      const label = svg("text", { x: 10, y: single ? 16 : 23 });
      label.textContent = truncateLabel(node.artifact.label, 30);
      group.appendChild(label);
      if (single) {
        const path = svg("text", { x: 10, y: 29, class: "sub" });
        path.setAttribute("font-size", "9.5");
        path.setAttribute("fill", "var(--muted)");
        path.textContent = truncateLabel(file, 32);
        group.appendChild(path);
      }
      const tip = svg("title");
      tip.textContent =
        node.artifact.path +
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
      // Kind accent: a colour bar plus the kind's name in the fact line below,
      // so the kind is never signalled by colour alone.
      group.appendChild(
        svg("rect", {
          x: 0,
          y: 0,
          width: 4,
          height: node.h,
          fill: kindColor(step.kind),
        })
      );

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

      if (step.stats) {
        const metric = svg("text", {
          class: "metric",
          x: node.w - 12,
          y: 55,
          "text-anchor": "end",
        });
        metric.textContent =
          fmtSeconds(step.stats.total_s) +
          " · " +
          fmtTokens(step.stats.input_tokens + step.stats.output_tokens);
        group.appendChild(metric);
        const runs = svg("text", {
          class: "metric",
          x: node.w - 12,
          y: 38,
          "text-anchor": "end",
        });
        runs.textContent = step.stats.calls + "×";
        group.appendChild(runs);
      }

      // The files the step writes belong to the step, not beside it: this is
      // where the pipeline's state actually changes.
      const files = state.showArtifacts ? step.outputs || [] : [];
      files.forEach((artifactId, index) => {
        const artifact = artifactById[artifactId];
        if (!artifact) return;
        const rowY = NODE_H + index * FILE_H;
        const row = svg("g", { class: "writes" });
        row.appendChild(
          svg("path", {
            class: "writes-rule",
            d: "M12 " + (rowY - 6) + " L" + (node.w - 12) + " " + (rowY - 6),
          })
        );
        const text = svg("text", { x: 16, y: rowY + 5 });
        text.textContent =
          "writes  " + truncateLabel(artifactFile(artifact), 32);
        row.appendChild(text);
        const tip = svg("title");
        tip.textContent =
          artifact.label + "\n" + artifact.path + "\n" + artifact.note;
        row.appendChild(tip);
        group.appendChild(row);
      });

      group.addEventListener("click", () => {
        select(step.id);
      });
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select(step.id);
        }
      });

      root.appendChild(group);
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
      host.style.minWidth = geometry.width + "px";
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
        : "Click any step for its prompt, output schema, dependencies and recorded calls.";

      /* The caption says only what the drawing cannot: what the unlabelled
         marks mean and what the figure does when it is touched. The layer
         semantics and the branch structure belong to the authored prose above,
         and repeating them here made the figure argue with the text. */
      const sourceCount = geometry.nodes.length - stepNodes.length;
      caption.innerHTML =
        "<b>Figure " +
        figureNumber +
        ".</b> " +
        escapeHtml(DATA.lanes[state.tab].label) +
        " pipeline as a dependency graph, " +
        stepNodes.length +
        " steps in " +
        geometry.layers +
        " layers. " +
        (sourceCount
          ? "Grey boxes are files this pipeline only reads, written by the " +
            "other one. "
          : "") +
        (geometry.bands.length
          ? "Hovering a shaded band names the concern its steps share. "
          : "") +
        "Selecting a step labels its arrows with the data that travels along " +
        "them, and a dashed arrow stands for a dependency whose intermediate " +
        "step the filters have hidden.";
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

    // Only what the prose above cannot say for itself: the entry point and the
    // size of the graph. The lane's own blurb is deliberately not repeated here
    //—the authored section introduces the pipeline, and saying it twice made
    // the figure look like it was arguing with the text.
    const lede = el("p", { class: "lane-lede" }, [
      el("span", { text: "Entry point " }),
      el("code", { class: "entry", text: lane.entry }),
      el("span", {
        text:
          " · " +
          stepsInTab().length +
          " steps · " +
          Object.keys(DATA.kinds).filter((kind) => {
            return stepsInTab().some((step) => {
              return step.kind === kind;
            });
          }).length +
          " step kinds",
      }),
    ]);

    host.appendChild(lede);
    host.appendChild(el("div", { class: "toolbar" }, [search, filters]));
    host.appendChild(hint);
    host.appendChild(
      el("figure", { class: "figure" }, [
        el("div", { class: "chart-scroll" }, [flow]),
        caption,
      ])
    );

    renderToolbar();
    draw();

    instance.clearSelection = function () {
      if (state.selected === null) return;
      state.selected = null;
      draw();
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

  function recordedCallsFor(stepId) {
    const out = [];
    ((DATA.runs && DATA.runs.runs) || []).forEach((run) => {
      (run.calls || []).forEach((call) => {
        if (call.step === stepId) out.push({ run: run.label, call: call });
      });
    });
    return out;
  }

  function callBlock(entry, index) {
    const call = entry.call;
    const inner = el("div", { class: "inner" });
    const usage = call.usage || {};
    inner.appendChild(
      el("p", { class: "sub" }, [
        el("span", {
          text:
            call.model +
            (call.reasoning_effort
              ? " · effort " + call.reasoning_effort
              : "") +
            " · " +
            fmtSeconds(call.duration_s) +
            (usage.input_tokens || usage.prompt_tokens
              ? " · " +
                fmtInt(usage.input_tokens || usage.prompt_tokens) +
                " in / " +
                fmtInt(usage.output_tokens || usage.completion_tokens || 0) +
                " out"
              : ""),
        }),
      ])
    );
    (call.messages || []).forEach((message) => {
      const note =
        message.full_length > message.content.length
          ? " (" + fmtInt(message.full_length) + " chars, elided)"
          : "";
      inner.appendChild(
        el("details", { class: "block" }, [
          el("summary", { text: message.role + note }),
          el("div", { class: "inner" }, [
            el("pre", { class: "prompt", text: message.content }),
          ]),
        ])
      );
    });
    const result = call.result || {};
    if (result.text) {
      inner.appendChild(
        el("details", { class: "block" }, [
          el("summary", { text: "response (" + result.kind + ")" }),
          el("div", { class: "inner" }, [
            el("pre", { class: "prompt", text: result.text }),
          ]),
        ])
      );
    }
    return el("details", { class: "block" }, [
      el("summary", {
        text:
          "Call " +
          (index + 1) +
          "—" +
          entry.run +
          "—" +
          fmtSeconds(call.duration_s),
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

  function renderDrawer(step) {
    const head = document.getElementById("drawer-title");
    head.textContent = step.label;
    const body = document.getElementById("drawer-body");
    clear(body);

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
      factRow(
        "Reads",
        (step.inputs || [])
          .map((id) => {
            return artifactById[id] ? escapeHtml(artifactById[id].label) : id;
          })
          .join(", ") || null
      ),
      factRow(
        "Writes",
        (step.outputs || [])
          .map((id) => {
            return artifactById[id] ? escapeHtml(artifactById[id].label) : id;
          })
          .join(", ") || null
      ),
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
            "grey lines above a block are the conditions that guard it.",
        })
      );
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

    const calls = recordedCallsFor(step.id);
    body.appendChild(el("h3", { text: "Recorded run" }));
    if (!calls.length) {
      body.appendChild(
        el("div", {
          class: "empty",
          html:
            "No recorded calls for this step. Capture a run with " +
            '<code>python scripts/record_pipeline_run.py person "Ada Lovelace"</code> ' +
            "and rebuild.",
        })
      );
    } else {
      const stats = step.stats || {};
      body.appendChild(
        el("p", {
          class: "sub",
          text:
            calls.length +
            " call(s) · " +
            fmtSeconds(stats.total_s) +
            " total · median " +
            fmtSeconds(stats.median_s) +
            " · " +
            fmtInt(stats.input_tokens) +
            " in / " +
            fmtInt(stats.output_tokens) +
            " out tokens" +
            (stats.reasoning_tokens
              ? " (" + fmtInt(stats.reasoning_tokens) + " reasoning)"
              : ""),
        })
      );
      calls.slice(0, 6).forEach((entry, index) => {
        body.appendChild(callBlock(entry, index));
      });
      if (calls.length > 6) {
        body.appendChild(
          el("p", {
            class: "sub",
            text: "Showing the first 6 of " + calls.length + " calls.",
          })
        );
      }
    }
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

  /* ------------------------------------------------- shared computed parts */

  function stepsOf(laneId) {
    return DATA.steps.filter((step) => {
      return step.column === laneId;
    });
  }

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

     A caption states what the block is and then only what the block cannot
     show for itself; whatever a legend, an axis or the prose above already
     says is left out. Both parts are written as sentences, so the terminating
     full stop is added here rather than trusted to every call site. */
  function caption(kind, number, title, sub) {
    return el("div", { class: "cap" }, [
      el("p", { class: "cap-title" }, [
        el("b", { text: kind + " " + number + "." }),
        el("span", { text: " " + sentence(title) }),
      ]),
      sub ? el("p", { class: "cap-sub", text: sentence(sub) }) : null,
    ]);
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

  // Only the kinds that actually appear get a legend entry—naming hues that
  // are not on screen makes the reader hunt for them.
  function kindLegend(steps) {
    const present = new Set(
      steps.map((step) => {
        return step.kind;
      })
    );
    const legend = el("div", { class: "legend" });
    Object.entries(DATA.kinds).forEach((entry) => {
      if (!present.has(entry[0])) return;
      legend.appendChild(
        el("span", { class: "item" }, [
          el("span", {
            class: "swatch",
            style: "background:" + kindColor(entry[0]),
          }),
          el("span", { text: entry[1].label }),
        ])
      );
    });
    return legend;
  }

  function barChart(host, rows, options) {
    const max =
      rows.reduce((best, row) => {
        return Math.max(best, row.total);
      }, 0) || 1;
    const grid = el("div", { class: "bars" });
    rows.forEach((row) => {
      grid.appendChild(
        el("div", { class: "name", title: row.name, text: row.name })
      );
      const track = el("div", {
        class: "track",
        title: row.name + "—" + options.format(row.total),
      });
      (row.parts || [{ value: row.total, color: row.color }]).forEach(
        (part) => {
          if (!part.value) return;
          track.appendChild(
            el("div", {
              class: "seg" + (part.tinted ? " tinted" : ""),
              style:
                "width:" +
                ((part.value / max) * 100).toFixed(2) +
                "%;background:" +
                part.color,
              title: part.label
                ? row.name +
                  "—" +
                  part.label +
                  ": " +
                  options.format(part.value)
                : options.format(part.value),
            })
          );
        }
      );
      grid.appendChild(track);
      grid.appendChild(
        el("div", { class: "val", text: options.format(row.total) })
      );
    });
    host.appendChild(grid);
  }

  function recordedRunsFor(laneId) {
    const used = {};
    ((DATA.runs && DATA.runs.runs) || []).forEach((run) => {
      (run.calls || []).forEach((call) => {
        const step = stepById[call.step];
        if (step && step.column === laneId) used[run.label] = run;
      });
    });
    return Object.values(used);
  }

  /* The report mounts several run blocks per pipeline, and with no recording on
     disk each of them would otherwise print the same paragraph of instructions.
     The first block for a lane explains itself; the rest only say what is
     missing. */
  const noRunExplained = new Set();

  function noRunNote(laneId) {
    if (noRunExplained.has(laneId)) {
      return emptyNote(
        "Nothing to show—no run has been recorded for the " +
          escapeHtml(laneLabel(laneId).toLowerCase()) +
          " pipeline."
      );
    }
    noRunExplained.add(laneId);
    const other = laneId === "person" ? "meta" : "person";
    const elsewhere = recordedRunsFor(other).length;
    return emptyNote(
      "<strong>No run recorded for the " +
        escapeHtml(laneLabel(laneId).toLowerCase()) +
        " pipeline yet.</strong><br>Everything shown for it comes from static " +
        "analysis, so the prompts are templates and there are no timings or " +
        "token counts. To add them, run a real generation under the " +
        "recorder:<br><br><code>python scripts/record_pipeline_run.py " +
        escapeHtml(laneId) +
        ' "' +
        (laneId === "person" ? "Ada Lovelace" : "Computing Pioneers") +
        '"</code><br><br>' +
        "Then rebuild with <code>python scripts/generate_report.py</code>. " +
        "Recording performs real API calls and rewrites that subject's data " +
        "files." +
        (elsewhere
          ? "<br><br>Runs do exist for the " +
            escapeHtml(laneLabel(other).toLowerCase()) +
            " pipeline."
          : "")
    );
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
        mount.appendChild(el("p", { class: "cap-sub", text: params.caption }));
      }
    },

    pipeline: function (mount, params, numbers) {
      createChart(mount, params.lane, numbers.figure);
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

    artifacts: function (mount, params, numbers) {
      const steps = stepsOf(params.lane);
      const touched = {};
      steps.forEach((step) => {
        (step.outputs || []).forEach((id) => {
          touched[id] = touched[id] || { writes: [], reads: [] };
          touched[id].writes.push(step.label);
        });
        (step.inputs || []).forEach((id) => {
          touched[id] = touched[id] || { writes: [], reads: [] };
          touched[id].reads.push(step.label);
        });
      });

      mount.appendChild(
        caption(
          "Table",
          numbers.table,
          "Files the " +
            laneLabel(params.lane).toLowerCase() +
            " pipeline reads and writes"
        )
      );
      mount.appendChild(
        dataTable(
          ["File", "Kind", "Written by", "Read by"],
          DATA.artifacts
            .filter((artifact) => {
              return touched[artifact.id];
            })
            .map((artifact) => {
              const use = touched[artifact.id];
              return [
                el("td", {}, [
                  el("div", { text: artifact.label }),
                  el("div", { class: "path" }, [code(artifact.path)]),
                ]),
                plain(artifact.kind),
                plain(use.writes.join(", ") || "—"),
                plain(use.reads.join(", ") || "—"),
              ];
            })
        )
      );
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

    runfigures: function (mount, params, numbers) {
      const withStats = stepsOf(params.lane).filter((step) => {
        return step.stats;
      });
      if (!withStats.length) {
        mount.appendChild(noRunNote(params.lane));
        return;
      }

      const used = recordedRunsFor(params.lane);
      mount.appendChild(
        el("p", {
          class: "cap-sub",
          text:
            "Measured from " +
            used
              .map((run) => {
                return run.label + " (" + run.recorded_at + ")";
              })
              .join(", ") +
            ".",
        })
      );

      const timeCard = el("div", { class: "chart-card" }, [
        caption(
          "Figure",
          numbers.figure,
          "API time per step, " + laneLabel(params.lane).toLowerCase(),
          "A bar totals the wall-clock time of every call the step made, so a " +
            "step that runs once per event is long by repetition rather than " +
            "by latency"
        ),
        kindLegend(withStats),
      ]);
      barChart(
        timeCard,
        withStats
          .slice()
          .sort((a, b) => {
            return b.stats.total_s - a.stats.total_s;
          })
          .map((step) => {
            return {
              name: step.label,
              total: step.stats.total_s,
              color: kindColor(step.kind),
            };
          }),
        { format: fmtSeconds }
      );
      mount.appendChild(timeCard);

      const tokenCard = el("div", { class: "chart-card" }, [
        caption(
          "Figure",
          numbers.figure + 1,
          "Tokens per step, " + laneLabel(params.lane).toLowerCase(),
          "A bar totals the same calls, so a prompt that is re-sent for every " +
            "event is counted once per call"
        ),
        el("div", { class: "legend" }, [
          el("span", { class: "item" }, [
            el("span", { class: "swatch", style: "background:var(--ink-2)" }),
            el("span", { text: "input tokens (solid)" }),
          ]),
          el("span", { class: "item" }, [
            el("span", {
              class: "swatch tinted",
              style: "background:var(--ink-2);opacity:.42",
            }),
            el("span", { text: "output tokens (pale)" }),
          ]),
        ]),
      ]);
      barChart(
        tokenCard,
        withStats
          .slice()
          .sort((a, b) => {
            return (
              b.stats.input_tokens +
              b.stats.output_tokens -
              (a.stats.input_tokens + a.stats.output_tokens)
            );
          })
          .map((step) => {
            return {
              name: step.label,
              total: step.stats.input_tokens + step.stats.output_tokens,
              parts: [
                {
                  value: step.stats.input_tokens,
                  color: kindColor(step.kind),
                  label: "input",
                },
                {
                  value: step.stats.output_tokens,
                  color: kindColor(step.kind),
                  tinted: true,
                  label: "output",
                },
              ],
            };
          }),
        { format: fmtTokens }
      );
      mount.appendChild(tokenCard);
    },

    runtable: function (mount, params, numbers) {
      const withStats = stepsOf(params.lane).filter((step) => {
        return step.stats;
      });
      if (!withStats.length) {
        mount.appendChild(noRunNote(params.lane));
        return;
      }
      mount.appendChild(
        caption(
          "Table",
          numbers.table,
          "Recorded calls per step, " + laneLabel(params.lane).toLowerCase()
        )
      );
      mount.appendChild(
        dataTable(
          [
            "Step",
            "Kind",
            "Calls",
            "Total",
            "Median",
            "Slowest",
            "In",
            "Out",
            "Errors",
          ],
          withStats.map((step) => {
            return [
              plain(step.label),
              el("td", {}, [
                el("span", {
                  class: "swatch",
                  style: "background:" + kindColor(step.kind),
                }),
                el("span", { text: DATA.kinds[step.kind].label }),
              ]),
              plain(String(step.stats.calls)),
              plain(fmtSeconds(step.stats.total_s)),
              plain(fmtSeconds(step.stats.median_s)),
              plain(fmtSeconds(step.stats.max_s)),
              plain(fmtInt(step.stats.input_tokens)),
              plain(fmtInt(step.stats.output_tokens)),
              plain(step.stats.errors ? String(step.stats.errors) : "—"),
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
          entry.script + "—" + entry.flags.length + " options"
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
        const count = DATA.steps.filter((step) => {
          return step.kind === entry[0];
        }).length;
        list.appendChild(
          el("dt", {}, [
            el("span", {
              class: "swatch",
              style: "background:" + kindColor(entry[0]),
            }),
            el("span", { text: entry[1].label }),
            el("span", { class: "count", text: count + " steps" }),
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
      const unattributed = DATA.unattributed || [];
      mount.appendChild(
        el("p", { class: "cap-sub" }, [
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
      if (unattributed.length) {
        mount.appendChild(
          emptyNote(
            unattributed.length +
              " recorded call(s) could not be attributed to a documented " +
              "step: " +
              escapeHtml(
                unattributed
                  .map((item) => {
                    return item.origin;
                  })
                  .join(", ")
              ) +
              ". That usually means a helper calls the model outside the " +
              "function spec.py names."
          )
        );
      }
    },
  };

  /* --------------------------------------------------------- page chrome */

  function renderMetaRow() {
    const host = document.getElementById("meta-row");
    if (!host) return;
    const chips = [
      ["Built", DATA.generated_at],
      ["Commit", DATA.commit || "—"],
      ["Steps", String(DATA.totals.steps)],
    ];
    chips.forEach((chip) => {
      host.appendChild(
        el("span", { class: "chip" }, [
          el("span", { text: chip[0] }),
          el("code", { text: chip[1] }),
        ])
      );
    });

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
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDrawer();
  });

  renderMetaRow();
  hydrate();
  renderRail();
})();
