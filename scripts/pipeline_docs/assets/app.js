/* Pipeline documentation — rendering and interaction.
   The page is a pure function of window.PIPELINE, which the Python build emits.
   Layout runs client-side so filters can re-flow the chart. */

(function () {
  "use strict";

  const DATA = window.PIPELINE;
  const SVG_NS = "http://www.w3.org/2000/svg";

  const NODE_W = 252;
  const NODE_H = 76;
  const ROW_GAP = 46;
  const COL_GAP = 74;
  const ART_W = 172;
  const ART_H = 34;
  const ART_GAP = 16;
  const PAD = 16;
  const HEAD_H = 62;
  const COL_W = NODE_W + ART_GAP + ART_W;

  const state = {
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

  function kindColor(kind) {
    return "var(--kind-" + kind + ")";
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
          el("span", { text: chip[0] + ":" }),
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

  /* ------------------------------------------------------------ toolbar */

  function renderToolbar() {
    const host = document.getElementById("filters");

    Object.entries(DATA.kinds).forEach((entry) => {
      const kind = entry[0];
      const info = entry[1];
      const button = el("button", {
        class: "toggle",
        type: "button",
        "aria-pressed": "true",
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
      "aria-pressed": "true",
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
      "aria-pressed": "true",
      title: "Show the files each step writes.",
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

    const search = document.getElementById("search");
    search.addEventListener("input", () => {
      state.query = search.value.trim().toLowerCase();
      draw();
    });
  }

  /* -------------------------------------------------------------- chart */

  function layout() {
    const columns = ["person", "meta"];
    const placed = [];
    const chips = [];
    let maxY = 0;

    columns.forEach((column, columnIndex) => {
      const colX = PAD + columnIndex * (COL_W + COL_GAP);
      const steps = DATA.steps
        .filter((step) => {
          return step.column === column && matchesFilters(step);
        })
        .sort((a, b) => {
          return a.stage - b.stage || a._order - b._order;
        });

      let y = HEAD_H;
      steps.forEach((step, index) => {
        const outputs = state.showArtifacts ? step.outputs || [] : [];
        placed.push({
          step: step,
          x: colX,
          y: y,
          column: column,
          prev: index > 0 ? steps[index - 1] : null,
          sameStageAsPrev: index > 0 && steps[index - 1].stage === step.stage,
        });
        outputs.forEach((artifactId, chipIndex) => {
          chips.push({
            artifact: artifactById[artifactId],
            stepId: step.id,
            x: colX + NODE_W + ART_GAP,
            y: y + chipIndex * (ART_H + 6),
          });
        });
        const blockHeight = Math.max(NODE_H, outputs.length * (ART_H + 6) - 6);
        y += blockHeight + ROW_GAP;
        maxY = Math.max(maxY, y);
      });
    });

    return {
      placed: placed,
      chips: chips,
      width: PAD * 2 + COL_W * 2 + COL_GAP,
      height: maxY + PAD,
    };
  }

  function drawNode(root, item) {
    const step = item.step;
    const dim = !matchesQuery(step);
    const group = svg("g", {
      class:
        "node" +
        (dim ? " dim" : "") +
        (state.selected === step.id ? " selected" : ""),
      transform: "translate(" + item.x + "," + item.y + ")",
      tabindex: "0",
      role: "button",
      "aria-label": step.label + " — " + DATA.kinds[step.kind].label,
    });

    group.appendChild(
      svg("rect", { class: "body", width: NODE_W, height: NODE_H, rx: 11 })
    );
    // Kind accent: a colour bar plus the badge text below, so the kind is
    // never signalled by colour alone.
    const accent = svg("path", {
      d:
        "M0 11 A11 11 0 0 1 11 0 L11 " +
        NODE_H +
        " A11 11 0 0 1 0 " +
        (NODE_H - 11) +
        " Z",
      fill: kindColor(step.kind),
    });
    group.appendChild(accent);

    const title = svg("text", { class: "title", x: 22, y: 25 });
    title.textContent = truncateLabel(step.label, 32);
    group.appendChild(title);

    const sub = svg("text", { class: "sub", x: 22, y: 43 });
    sub.textContent = truncateLabel(step.script.replace(".py", ""), 30);
    group.appendChild(sub);

    const facts = [];
    if (step.phase) facts.push(step.phase);
    facts.push(DATA.kinds[step.kind].label);
    if (step.lane === "shared") facts.push("shared");
    if (step.calls_per_run && step.calls_per_run !== "1") facts.push("×N");
    const factLine = svg("text", { class: "metric", x: 22, y: 62 });
    factLine.textContent = facts.join(" · ");
    group.appendChild(factLine);

    if (step.stats) {
      const metric = svg("text", {
        class: "metric",
        x: NODE_W - 12,
        y: 62,
        "text-anchor": "end",
      });
      metric.textContent =
        fmtSeconds(step.stats.total_s) +
        " · " +
        fmtTokens(step.stats.input_tokens + step.stats.output_tokens);
      group.appendChild(metric);
      const badge = svg("text", {
        class: "metric",
        x: NODE_W - 12,
        y: 25,
        "text-anchor": "end",
      });
      badge.textContent = step.stats.calls + "×";
      group.appendChild(badge);
    }

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

  function drawChip(root, chip) {
    if (!chip.artifact) return;
    const step = stepById[chip.stepId];
    const related =
      state.selected &&
      (state.selected === chip.stepId ||
        (stepById[state.selected].inputs || []).indexOf(chip.artifact.id) !==
          -1);
    const group = svg("g", {
      class:
        "artifact" +
        (related ? " related" : "") +
        (matchesQuery(step) ? "" : " dim"),
      transform: "translate(" + chip.x + "," + chip.y + ")",
    });
    group.appendChild(svg("rect", { width: ART_W, height: ART_H, rx: 8 }));
    const label = svg("text", { x: 10, y: 15 });
    label.textContent = truncateLabel(chip.artifact.label, 24);
    group.appendChild(label);
    const path = svg("text", { x: 10, y: 27, class: "sub" });
    path.setAttribute("font-size", "9.5");
    path.setAttribute("fill", "var(--muted)");
    path.textContent = truncateLabel(
      chip.artifact.path.split(",")[0].split("/").slice(-1)[0],
      26
    );
    group.appendChild(path);
    const tip = svg("title");
    tip.textContent = chip.artifact.path + "\n" + chip.artifact.note;
    group.appendChild(tip);
    root.appendChild(group);
  }

  function drawEdges(root, placed) {
    const byColumn = {};
    placed.forEach((item) => {
      (byColumn[item.column] = byColumn[item.column] || []).push(item);
    });
    Object.values(byColumn).forEach((items) => {
      for (let index = 1; index < items.length; index += 1) {
        const from = items[index - 1];
        const to = items[index];
        const x = from.x + NODE_W / 2;
        const y1 = from.y + NODE_H;
        const y2 = to.y;
        const line = svg("path", {
          class: "edge",
          d: "M" + x + " " + y1 + " L" + x + " " + (y2 - 7),
          "stroke-dasharray": to.sameStageAsPrev ? "4 4" : null,
        });
        root.appendChild(line);
        root.appendChild(
          svg("path", {
            class: "edge-arrow",
            d:
              "M" +
              (x - 4) +
              " " +
              (y2 - 7) +
              " L" +
              (x + 4) +
              " " +
              (y2 - 7) +
              " L" +
              x +
              " " +
              y2 +
              " Z",
          })
        );
      }
    });
  }

  function drawColumnHeads(root) {
    ["person", "meta"].forEach((column, index) => {
      const lane = DATA.lanes[column];
      const x = PAD + index * (COL_W + COL_GAP);
      const title = svg("text", { class: "lane-title", x: x, y: 18 });
      title.textContent = lane.label;
      root.appendChild(title);
      const sub = svg("text", { class: "lane-sub", x: x, y: 36 });
      sub.textContent = lane.entry;
      root.appendChild(sub);
    });
  }

  function draw() {
    const host = document.getElementById("flow");
    while (host.firstChild) host.removeChild(host.firstChild);

    const geometry = layout();
    host.setAttribute(
      "viewBox",
      "0 0 " + geometry.width + " " + geometry.height
    );
    host.setAttribute("width", geometry.width);
    host.setAttribute("height", geometry.height);

    drawColumnHeads(host);
    drawEdges(host, geometry.placed);
    geometry.chips.forEach((chip) => {
      drawChip(host, chip);
    });
    geometry.placed.forEach((item) => {
      drawNode(host, item);
    });

    const visible = geometry.placed.filter((item) => {
      return matchesQuery(item.step);
    }).length;
    document.getElementById("hint").textContent = state.query
      ? visible +
        " of " +
        geometry.placed.length +
        " visible steps match “" +
        state.query +
        "”"
      : "Click any step for its prompt, output schema and recorded calls. Dashed connectors link steps that run in the same phase.";
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

  function renderDrawer(step) {
    const head = document.getElementById("drawer-title");
    head.textContent = step.label;
    const body = document.getElementById("drawer-body");
    while (body.firstChild) body.removeChild(body.firstChild);

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
      factRow("Phase", step.phase ? escapeHtml(step.phase) : null),
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
      const track = el("div", { class: "track" });
      (row.parts || [{ value: row.total, color: "var(--series-1)" }]).forEach(
        (part) => {
          if (!part.value) return;
          track.appendChild(
            el("div", {
              class: "seg",
              style:
                "width:" +
                ((part.value / max) * 100).toFixed(2) +
                "%;background:" +
                part.color,
              title: part.label
                ? part.label + ": " + options.format(part.value)
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
    const runs = (DATA.runs && DATA.runs.runs) || [];
    if (!runs.length) {
      host.appendChild(
        el("div", {
          class: "empty",
          html:
            "<strong>No run recorded yet.</strong><br>The chart above is built from " +
            "static analysis alone, so it shows prompt templates but no real " +
            "prompts, timings or token counts. To add them, run a real generation " +
            'under the recorder:<br><br><code>python scripts/record_pipeline_run.py person "Ada Lovelace"</code><br>' +
            '<code>python scripts/record_pipeline_run.py meta "Computing Pioneers"</code><br><br>' +
            "Then rebuild with <code>python scripts/generate_pipeline_docs.py</code>. " +
            "Recording performs real API calls and rewrites that subject's data files.",
        })
      );
      return;
    }

    host.appendChild(
      el("p", { class: "section-lede" }, [
        el("span", {
          text:
            "From " +
            runs
              .map((run) => {
                return run.label + " (" + run.recorded_at + ")";
              })
              .join(", ") +
            ". Times are wall-clock per API call; token counts come from the " +
            "API's own usage reporting.",
        }),
      ])
    );

    const withStats = DATA.steps
      .filter((step) => {
        return step.stats;
      })
      .slice();

    const timeRows = withStats
      .slice()
      .sort((a, b) => {
        return b.stats.total_s - a.stats.total_s;
      })
      .map((step) => {
        return {
          name: step.label,
          total: step.stats.total_s,
          parts: [{ value: step.stats.total_s, color: "var(--series-1)" }],
        };
      });

    const timeCard = el("div", { class: "chart-card" }, [
      el("h3", { text: "API time per step" }),
      el("p", {
        class: "sub",
        text: "Total seconds spent waiting on the model, summed over every call the step made.",
      }),
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
              color: "var(--series-1)",
              label: "input",
            },
            {
              value: step.stats.output_tokens,
              color: "var(--series-2)",
              label: "output",
            },
          ],
        };
      });

    const tokenCard = el("div", { class: "chart-card" }, [
      el("h3", { text: "Tokens per step" }),
      el("p", { class: "sub", text: "Input and output tokens, stacked." }),
      el("div", { class: "legend" }, [
        el("span", {}, [
          el("span", { class: "swatch", style: "background:var(--series-1)" }),
          el("span", { text: "input" }),
        ]),
        el("span", {}, [
          el("span", { class: "swatch", style: "background:var(--series-2)" }),
          el("span", { text: "output" }),
        ]),
      ]),
    ]);
    barChart(tokenCard, tokenRows, { format: fmtTokens });
    host.appendChild(tokenCard);

    const table = el("table", { class: "data" });
    table.appendChild(
      el("tr", {}, [
        el("th", { text: "Step" }),
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
        el("h3", { text: "Every recorded step" }),
        el("p", {
          class: "sub",
          text: "The same numbers as a table, in pipeline order.",
        }),
        table,
      ])
    );

    if ((DATA.unattributed || []).length) {
      host.appendChild(
        el("div", { class: "empty" }, [
          el("span", {
            text:
              DATA.unattributed.length +
              " recorded call(s) could not be attributed to a documented step: " +
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
    DATA.entrypoints.forEach((entry) => {
      const inner = el("div", { class: "inner" });
      if (entry.docstring) {
        inner.appendChild(el("p", { class: "sub", text: entry.docstring }));
      }
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
      inner.appendChild(table);
      host.appendChild(
        el("details", { class: "block" }, [
          el("summary", {
            text: entry.script + " — " + entry.flags.length + " options",
          }),
          inner,
        ])
      );
    });
  }

  /* --------------------------------------------------------------- init */

  document
    .getElementById("drawer-close")
    .addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDrawer();
  });

  renderHeader();
  renderToolbar();
  renderRuns();
  renderAppendix();
  draw();
})();
