/* Pipeline documentation — rendering and interaction.
   The page is a pure function of window.PIPELINE, which the Python build emits.
   Layout runs client-side so filters can re-flow the chart.

   One pipeline is shown at a time: the tab selects it, and the chart, the run
   charts and the entry-point appendix are all rebuilt for that pipeline only.
   Colour encodes the step kind and nothing else.

   The chart is a layered DAG, not a sequence. A step's layer is the longest
   path of real data dependencies reaching it, so steps drawn side by side are
   genuinely independent — the map branch and the network branch of the meta
   story really do run without seeing each other. Files a step writes are drawn
   inside its node; files that arrive from the other pipeline become source
   nodes, since nothing in this chart produces them.

   The vertical axis is the dependency graph; the horizontal axis is free, and
   `spec.GROUPS` spends it on meaning. Steps of one concern — planning image
   searches, running them, matching the results, generating the portrait — are
   aligned in one column and banded, so a job that takes four layers reads as
   one vertical strand instead of drifting across the chart. */

(function () {
  "use strict";

  const DATA = window.PIPELINE;
  const SVG_NS = "http://www.w3.org/2000/svg";

  const COLUMNS = ["person", "meta"];

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

  const state = {
    tab: COLUMNS[0],
    kinds: new Set(Object.keys(DATA.kinds)),
    showShared: true,
    showArtifacts: true,
    query: "",
    selected: null,
  };

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

  /* ------------------------------------------------------------- header */

  function renderHeader() {
    const meta = document.getElementById("meta-row");
    const chips = [
      ["Generated", DATA.generated_at],
      ["Commit", DATA.commit || "—"],
      [
        "Scripts scanned",
        DATA.totals.scripts +
          " (" +
          fmtInt(DATA.totals.script_lines) +
          " lines)",
      ],
      ["Model call sites", String(DATA.totals.call_sites)],
    ];
    chips.forEach((chip) => {
      meta.appendChild(
        el("span", { class: "chip" }, [
          el("span", { text: chip[0] }),
          el("code", { text: chip[1] }),
        ])
      );
    });

    const runs = (DATA.runs && DATA.runs.runs) || [];
    const totalCalls = runs.reduce((sum, run) => {
      return sum + (run.calls || []).length;
    }, 0);
    let apiSeconds = 0;
    let tokens = 0;
    runs.forEach((run) => {
      (run.calls || []).forEach((call) => {
        apiSeconds += Number(call.duration_s || 0);
        const usage = call.usage || {};
        tokens +=
          Number(usage.input_tokens || usage.prompt_tokens || 0) +
          Number(usage.output_tokens || usage.completion_tokens || 0);
      });
    });

    const tiles = [
      [String(DATA.totals.steps), "documented steps"],
      [String(DATA.totals.ai_steps), "of them call a model"],
      [runs.length ? String(totalCalls) : "—", "recorded model calls"],
      [runs.length ? fmtSeconds(apiSeconds) : "—", "recorded API time"],
      [runs.length ? fmtTokens(tokens) : "—", "recorded tokens"],
    ];
    const host = document.getElementById("tiles");
    tiles.forEach((tile) => {
      host.appendChild(
        el("div", { class: "tile" }, [
          el("div", { class: "value", text: tile[0] }),
          el("div", { class: "label", text: tile[1] }),
        ])
      );
    });
  }

  /* --------------------------------------------------------- story tabs */

  function renderTabs() {
    const host = document.getElementById("pipeline-tabs");
    clear(host);
    COLUMNS.forEach((column) => {
      const lane = DATA.lanes[column];
      const count = DATA.steps.filter((step) => {
        return step.column === column;
      }).length;
      const button = el("button", {
        class: "pipeline-tab",
        type: "button",
        role: "tab",
        "aria-selected": state.tab === column ? "true" : "false",
        onclick: function () {
          if (state.tab === column) return;
          state.tab = column;
          state.selected = null;
          document.getElementById("drawer").classList.remove("open");
          renderTabs();
          renderPanel();
        },
      });
      button.appendChild(el("span", { text: lane.label }));
      button.appendChild(
        el("span", { class: "count", text: count + " steps" })
      );
      host.appendChild(button);
    });
  }

  function renderPanelLede() {
    const lane = DATA.lanes[state.tab];
    const host = document.getElementById("panel-lede");
    clear(host);
    host.appendChild(el("span", { text: lane.blurb + " " }));
    host.appendChild(el("span", { text: "Entry point: " }));
    host.appendChild(el("code", { class: "entry", text: lane.entry }));
    host.appendChild(el("span", { text: "." }));
  }

  /* ------------------------------------------------------------ toolbar */

  function renderToolbar() {
    const host = document.getElementById("filters");
    clear(host);

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
        el("span", { class: "swatch", style: "background:" + kindColor(kind) })
      );
      button.appendChild(el("span", { text: info.label }));
      host.appendChild(button);
    });

    const shared = el("button", {
      class: "toggle",
      type: "button",
      "aria-pressed": state.showShared ? "true" : "false",
      title: "Steps that belong to shared subsystems rather than one pipeline.",
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
    host.appendChild(shared);

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
    host.appendChild(artifacts);
  }

  /* -------------------------------------------------------------- chart */

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
      resolveDeps(parent, visibleIds, seen.concat([dep.on])).forEach((edge) => {
        out.push({ from: edge.from, data: edge.data, indirect: true });
      });
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

  /* Horizontal placement. The layer decides how far *down* a node goes; the
     graph says nothing about how far across, so that freedom is spent on
     meaning: the steps of one concern share a column and read as a single
     vertical strand.

     The unit that gets a column is not the node but the *entity* — a group, or
     an ungrouped node on its own. A group whose members all sit in different
     layers takes one column; if a filter or the graph puts two members in the
     same layer, it takes that many adjacent columns and they fill left to
     right.

     Columns are shared by entities whose layer spans do not overlap, which is
     what keeps the chart from growing a column per node: alignment costs width
     only where a group actually reserves a strip. That same rule guarantees a
     group's strip is free of strangers over its whole height, so the band drawn
     behind it never encloses an unrelated step. */
  function assignColumns(rows) {
    const entities = [];
    const byKey = {};
    rows.forEach((row, layer) => {
      row.forEach((node, index) => {
        const groupId = node.type === "step" ? groupOfStep[node.id] : null;
        const key = groupId ? "g:" + groupId : "n:" + node.id;
        let entity = byKey[key];
        if (!entity) {
          entity = {
            group: groupId ? groupById[groupId] : null,
            members: [],
            byLayer: {},
            first: layer,
            last: layer,
            rank: 0,
          };
          byKey[key] = entity;
          entities.push(entity);
        }
        entity.members.push(node);
        (entity.byLayer[layer] = entity.byLayer[layer] || []).push(node);
        entity.first = Math.min(entity.first, layer);
        entity.last = Math.max(entity.last, layer);
        // Where the barycentre pass put this node in its row, normalized, so an
        // entity keeps the side of the chart its members were ordered onto.
        entity.rank += row.length > 1 ? index / (row.length - 1) : 0.5;
      });
    });

    entities.forEach((entity) => {
      entity.rank /= entity.members.length;
      entity.width = entity.members.reduce((best, node) => {
        return Math.max(best, node.w);
      }, 0);
      entity.slots = Object.keys(entity.byLayer).reduce((best, layer) => {
        return Math.max(best, entity.byLayer[layer].length);
      }, 1);
    });
    entities.sort((a, b) => {
      return a.rank - b.rank || a.first - b.first;
    });

    function sharesLayer(a, b) {
      return Object.keys(a.byLayer).some((layer) => {
        return b.byLayer[layer] !== undefined;
      });
    }

    const columns = [];
    const placed = [];
    entities.forEach((entity) => {
      function free(index) {
        return (columns[index] || []).every((other) => {
          return other.last < entity.first || entity.last < other.first;
        });
      }
      function fits(index) {
        for (let offset = 0; offset < entity.slots; offset += 1) {
          if (!free(index + offset)) return false;
        }
        return true;
      }

      // Everything already placed that shares a layer with this entity has a
      // lower rank, so it belongs to its left: that preserves the row order the
      // barycentre pass found.
      let start = 0;
      placed.forEach((other) => {
        if (sharesLayer(other, entity)) {
          start = Math.max(start, other.column + other.slots);
        }
      });
      while (!fits(start)) start += 1;

      entity.column = start;
      for (let offset = 0; offset < entity.slots; offset += 1) {
        columns[start + offset] = columns[start + offset] || [];
        columns[start + offset].push(entity);
      }
      placed.push(entity);
      Object.keys(entity.byLayer).forEach((layer) => {
        entity.byLayer[layer].forEach((node, index) => {
          node.slot = start + index;
        });
      });
    });

    const xOf = [];
    let cursor = PAD + RAIL_W + MARGIN_CH;
    for (let index = 0; index < columns.length; index += 1) {
      xOf[index] = cursor;
      cursor +=
        (columns[index] || []).reduce((best, entity) => {
          return Math.max(best, entity.width);
        }, 0) + COL_GAP;
    }

    return {
      entities: entities,
      xOf: xOf,
      width: Math.max(NODE_W, cursor - COL_GAP - (PAD + RAIL_W + MARGIN_CH)),
    };
  }

  /* The band behind a group. A single-member group is not worth a label — with
     a filter on, that is all a group may have left. */
  function groupBands(entities) {
    const bands = [];
    entities.forEach((entity) => {
      if (!entity.group || entity.members.length < 2) return;
      let x0 = Infinity;
      let x1 = -Infinity;
      let y0 = Infinity;
      let y1 = -Infinity;
      entity.members.forEach((node) => {
        x0 = Math.min(x0, node.x);
        x1 = Math.max(x1, node.x + node.w);
        y0 = Math.min(y0, node.y);
        y1 = Math.max(y1, node.y + node.h);
      });
      bands.push({
        group: entity.group,
        count: entity.members.length,
        x0: x0 - BAND_PAD,
        x1: x1 + BAND_PAD,
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

    const grid = assignColumns(rows);
    const contentW = grid.width;

    const nodes = [];
    const byId = {};
    const rails = [];
    let y = HEAD_H;
    rows.forEach((row, index) => {
      const rowH = row.reduce((best, node) => {
        return Math.max(best, node.h);
      }, 0);
      row.forEach((node) => {
        node.x = grid.xOf[node.slot];
        node.y = y;
        node.layer = index;
        nodes.push(node);
        byId[node.id] = node;
      });
      // Columns leave holes in sparse layers, so a row is no longer in
      // barycentre order; the edge fanning and the channel search below both
      // read rows left to right.
      row.sort((a, b) => {
        return a.x - b.x;
      });
      rails.push({ label: String(index + 1), y0: y, y1: y + rowH });
      y += rowH + LAYER_GAP;
    });

    const bands = groupBands(grid.entities);

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
        edge.x1 = edge.from.x + (edge.from.w * (index + 1)) / (list.length + 1);
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
     nodes in between. Each one is given a vertical channel — a column of empty
     space free across every layer it crosses — and routed down it. A group's
     band counts as occupied even where its column is empty: a line running
     down the middle of a band would read as belonging to it. */
  function routeLongEdges(edges, rows, contentW, bands) {
    const left = PAD + RAIL_W;
    const right = left + MARGIN_CH * 2 + contentW;
    const candidates = [left + MARGIN_CH / 2, right - MARGIN_CH / 2];
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
        if (!usable.length) return;
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
        " — " +
        band.count +
        " steps of one concern, aligned in one column" +
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
      "aria-label": step.label + " — " + DATA.kinds[step.kind].label,
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
    // Bare model id only — where it was resolved from belongs in the drawer.
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
      text.textContent = "writes  " + truncateLabel(artifactFile(artifact), 32);
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
    const host = document.getElementById("flow");
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
    document.getElementById("hint").textContent = state.query
      ? visible +
        " of " +
        stepNodes.length +
        " visible steps match “" +
        state.query +
        "”"
      : "Click any step for its prompt, output schema, dependencies and recorded calls.";

    const sourceCount = geometry.nodes.length - stepNodes.length;
    document.getElementById("flow-caption").innerHTML =
      "<b>Figure 1.</b> " +
      escapeHtml(DATA.lanes[state.tab].label) +
      " pipeline as a dependency graph — " +
      stepNodes.length +
      " steps in " +
      geometry.layers +
      " layers, read top to bottom. An arrow means one step consumes what the " +
      "step above it produced; a step's layer is the longest such chain " +
      "reaching it, so steps drawn side by side are independent and could run " +
      "in either order. " +
      (geometry.bands.length
        ? "A shaded band is one concern spread over several layers — its steps " +
          "are aligned in a single column, so the strand can be followed " +
          "straight down; hover the band for what holds it together. "
        : "") +
      "Click a step to label its arrows with the data that " +
      "travels along them. The colour bar gives the step kind, also written " +
      "out under the step name; the lines at the foot of a node are the files " +
      "it writes." +
      (sourceCount
        ? " Grey boxes are files this pipeline only reads — the other pipeline " +
          "writes them — and dotted arrows carry them in."
        : "") +
      " A dashed arrow means a filter has hidden an intermediate step and the " +
      "dependency is drawn straight through it.";
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
        text: name + " — " + (schema.fields || []).length + " fields",
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
          " — " +
          entry.run +
          " — " +
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
          "</b> — " +
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
        return (
          "<b>" + escapeHtml(other.label) + "</b> — " + escapeHtml(dep.data)
        );
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
                ? " <span class='sub'>— " +
                  escapeHtml(groupById[step.group].note) +
                  "</span>"
                : "")
          : null
      ),
      factRow("Phase", step.phase ? escapeHtml(step.phase) : null),
      factRow(
        "Needs",
        dependencyList(step) || "Nothing — this step starts a branch"
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

  function select(stepId) {
    state.selected = stepId;
    renderDrawer(stepById[stepId]);
    document.getElementById("drawer").classList.add("open");
    draw();
  }

  function closeDrawer() {
    state.selected = null;
    document.getElementById("drawer").classList.remove("open");
    draw();
  }

  /* --------------------------------------------------------- run charts */

  // Only the kinds that actually appear in the chart get a legend entry —
  // naming hues that are not on screen makes the reader hunt for them.
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
        title: row.name + " — " + options.format(row.total),
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
                  " — " +
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

  function renderRuns() {
    const host = document.getElementById("runs");
    clear(host);
    const runs = (DATA.runs && DATA.runs.runs) || [];
    const withStats = stepsInTab().filter((step) => {
      return step.stats;
    });

    if (!withStats.length) {
      const other = state.tab === "person" ? "meta" : "person";
      host.appendChild(
        el("div", {
          class: "empty",
          html:
            "<strong>No run recorded for the " +
            escapeHtml(DATA.lanes[state.tab].label.toLowerCase()) +
            " pipeline yet.</strong><br>The chart above is built from " +
            "static analysis alone, so it shows prompt templates but no real " +
            "prompts, timings or token counts. To add them, run a real generation " +
            "under the recorder:<br><br><code>python scripts/record_pipeline_run.py " +
            escapeHtml(state.tab) +
            ' "' +
            (state.tab === "person" ? "Ada Lovelace" : "Computing Pioneers") +
            '"</code><br><br>' +
            "Then rebuild with <code>python scripts/generate_pipeline_docs.py</code>. " +
            "Recording performs real API calls and rewrites that subject's data files." +
            (runs.length
              ? "<br><br>Recorded runs do exist for the " +
                escapeHtml(DATA.lanes[other].label.toLowerCase()) +
                " pipeline — see the other tab."
              : ""),
        })
      );
      return;
    }

    const used = {};
    runs.forEach((run) => {
      (run.calls || []).forEach((call) => {
        const step = stepById[call.step];
        if (step && step.column === state.tab) used[run.label] = run;
      });
    });
    host.appendChild(
      el("p", {
        class: "section-lede",
        text:
          "From " +
          Object.values(used)
            .map((run) => {
              return run.label + " (" + run.recorded_at + ")";
            })
            .join(", ") +
          ". Times are wall-clock per API call; token counts come from the " +
          "API's own usage reporting. Bars are coloured by step kind.",
      })
    );

    const timeRows = withStats
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
      });

    const timeCard = el("div", { class: "chart-card" }, [
      el("h3", { text: "Figure 2. API time per step" }),
      el("p", {
        class: "sub",
        text: "Total seconds spent waiting on the model, summed over every call the step made. Longest first.",
      }),
      kindLegend(withStats),
    ]);
    barChart(timeCard, timeRows, { format: fmtSeconds });
    host.appendChild(timeCard);

    const tokenRows = withStats
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
      });

    const tokenCard = el("div", { class: "chart-card" }, [
      el("h3", { text: "Figure 3. Tokens per step" }),
      el("p", {
        class: "sub",
        text: "Input and output tokens, stacked. Colour is the step kind, as above; the solid segment is input and the pale one output.",
      }),
      el("div", { class: "legend" }, [
        el("span", { class: "item" }, [
          el("span", {
            class: "swatch",
            style: "background:var(--ink-2)",
          }),
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
    barChart(tokenCard, tokenRows, { format: fmtTokens });
    host.appendChild(tokenCard);

    const table = el("table", { class: "data" });
    table.appendChild(
      el("tr", {}, [
        el("th", { text: "Step" }),
        el("th", { text: "Kind" }),
        el("th", { text: "Calls" }),
        el("th", { text: "Total" }),
        el("th", { text: "Median" }),
        el("th", { text: "Slowest" }),
        el("th", { text: "In" }),
        el("th", { text: "Out" }),
      ])
    );
    withStats.forEach((step) => {
      table.appendChild(
        el("tr", {}, [
          el("td", { text: step.label }),
          el("td", { class: "kind-cell" }, [
            el("span", {
              class: "swatch",
              style: "background:" + kindColor(step.kind),
            }),
            el("span", { text: DATA.kinds[step.kind].label }),
          ]),
          el("td", { text: String(step.stats.calls) }),
          el("td", { text: fmtSeconds(step.stats.total_s) }),
          el("td", { text: fmtSeconds(step.stats.median_s) }),
          el("td", { text: fmtSeconds(step.stats.max_s) }),
          el("td", { text: fmtInt(step.stats.input_tokens) }),
          el("td", { text: fmtInt(step.stats.output_tokens) }),
        ])
      );
    });
    host.appendChild(
      el("div", { class: "chart-card" }, [
        el("h3", { text: "Table 1. Every recorded step" }),
        el("p", {
          class: "sub",
          text: "The same numbers as a table, in pipeline order.",
        }),
        tableScroll(table),
      ])
    );

    const unattributed = (DATA.unattributed || []).length;
    if (unattributed) {
      host.appendChild(
        el("div", { class: "empty" }, [
          el("span", {
            text:
              unattributed +
              " recorded call(s) across both pipelines could not be attributed to a documented step: " +
              DATA.unattributed
                .map((item) => {
                  return item.origin;
                })
                .join(", ") +
              ". That usually means a helper calls the model outside the function spec.py names.",
          }),
        ])
      );
    }
  }

  /* ----------------------------------------------------------- appendix */

  function renderAppendix() {
    const host = document.getElementById("appendix");
    clear(host);
    DATA.entrypoints
      .filter((entry) => {
        return entry.lane === state.tab;
      })
      .forEach((entry) => {
        const table = el("table", { class: "data" });
        table.appendChild(
          el("tr", {}, [
            el("th", { text: "Flag" }),
            el("th", { text: "Default" }),
            el("th", { text: "What it does" }),
          ])
        );
        entry.flags.forEach((flag) => {
          table.appendChild(
            el("tr", {}, [
              el("td", {}, [el("code", { text: flag.flags.join(", ") })]),
              el("td", {
                text:
                  flag.default && flag.default !== "None" ? flag.default : "—",
              }),
              el("td", { text: flag.help || "" }),
            ])
          );
        });
        host.appendChild(
          el("div", { class: "chart-card" }, [
            el("h3", {
              text:
                "Table 2. " +
                entry.script +
                " — " +
                entry.flags.length +
                " options",
            }),
            entry.docstring
              ? el("p", { class: "sub", text: entry.docstring })
              : null,
            tableScroll(table),
          ])
        );
      });
  }

  /* --------------------------------------------------------------- init */

  function renderPanel() {
    renderPanelLede();
    renderRuns();
    renderAppendix();
    draw();
  }

  document
    .getElementById("drawer-close")
    .addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDrawer();
  });

  const search = document.getElementById("search");
  search.addEventListener("input", () => {
    state.query = search.value.trim().toLowerCase();
    draw();
  });

  renderHeader();
  renderToolbar();
  renderTabs();
  renderPanel();
})();
