<script>
  /*
   * The analysis page: loads every participant's log once, computes the
   * reports, and shows one of them — the aggregate, or one participant's —
   * chosen by the hash. The rail lists them; printing leaves the rail out.
   */
  import { onMount } from "svelte";
  import {
    aggregateReport,
    participantReport,
  } from "../../utils/evaluation/analysis.js";
  import {
    AnalysisKeyRequired,
    fetchLogs,
    fetchParticipants,
    rememberKey,
    storedKey,
  } from "./api.js";
  import AggregateReport from "./AggregateReport.svelte";
  import ParticipantReport from "./ParticipantReport.svelte";

  let status = $state("loading"); // loading | key | error | ready
  let errorMessage = $state("");
  let keyInput = $state("");
  let reports = $state([]);
  let aggregate = $state(null);
  let loadedAt = $state(null);
  let progress = $state({ done: 0, total: 0 });
  let hash = $state(typeof location !== "undefined" ? location.hash : "");

  const view = $derived.by(() => {
    const match = hash.match(/^#\/participant\/([^/?#]+)/);
    if (match) return { kind: "participant", id: decodeURIComponent(match[1]) };
    return { kind: "aggregate", id: null };
  });

  const current = $derived(
    view.kind === "participant"
      ? (reports.find((report) => report.id === view.id) ?? null)
      : null
  );

  async function load() {
    status = "loading";
    errorMessage = "";
    try {
      const participants = await fetchParticipants();
      progress = { done: 0, total: participants.length };
      const loaded = [];
      const queue = [...participants];
      // A few at a time: one request per participant, and a study has tens of
      // them, not thousands.
      const workers = Array.from({ length: 4 }, async () => {
        while (queue.length > 0) {
          const participant = queue.shift();
          // eslint-disable-next-line no-await-in-loop
          const batches = await fetchLogs(participant.id);
          loaded.push(participantReport(batches));
          progress = { done: progress.done + 1, total: progress.total };
        }
      });
      await Promise.all(workers);
      loaded.sort((a, b) =>
        a.id.localeCompare(b.id, undefined, { numeric: true })
      );
      reports = loaded;
      aggregate = aggregateReport(loaded);
      loadedAt = Date.now();
      status = "ready";
    } catch (error) {
      if (error instanceof AnalysisKeyRequired) {
        status = "key";
        return;
      }
      status = "error";
      errorMessage = String(error?.message ?? error);
    }
  }

  function submitKey(event) {
    event.preventDefault();
    rememberKey(keyInput.trim());
    load();
  }

  onMount(() => {
    keyInput = storedKey();
    const onHash = () => {
      hash = location.hash;
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onHash);
    load();
    return () => window.removeEventListener("hashchange", onHash);
  });
</script>

<div class="shell">
  <nav class="rail" aria-label="Reports">
    <p class="rail-title">Reports</p>
    <div class="rail-nav">
      <a class="rail-link" class:current={view.kind === "aggregate"} href="#/"
        ><span>All participants</span><span class="rail-count"
          >{reports.length}</span
        ></a
      >
      {#each reports as report (report.id)}
        <a
          class="rail-link"
          class:current={view.kind === "participant" && view.id === report.id}
          href="#/participant/{encodeURIComponent(report.id)}"
          ><span>{report.id}</span><span class="rail-count"
            >{report.totals.sessions}</span
          ></a
        >
      {/each}
    </div>
    <div class="rail-actions">
      <button class="control" type="button" onclick={load}>Reload logs</button>
      <button class="control" type="button" onclick={() => window.print()}
        >Print</button
      >
    </div>
    <p class="rail-foot">
      Life Data Stories · user evaluation
      {#if loadedAt}
        <br />loaded {new Date(loadedAt).toLocaleString("en-GB")}
      {/if}
    </p>
  </nav>

  <main class="page">
    {#if status === "loading"}
      <div class="state">
        Loading the logs{progress.total
          ? ` — ${progress.done} of ${progress.total} participants`
          : ""}…
      </div>
    {:else if status === "key"}
      <div class="state">
        This deployment protects its logs. Enter the analysis key (<code
          >EVALUATION_ANALYSIS_KEY</code
        >
        in the site's environment).
        <form class="key-form" onsubmit={submitKey}>
          <label for="analysis-key">Analysis key</label>
          <input id="analysis-key" type="password" bind:value={keyInput} />
          <button class="control" type="submit">Load</button>
        </form>
      </div>
    {:else if status === "error"}
      <div class="state state-error">
        The logs could not be loaded: {errorMessage}. Outside the evaluation
        deployment the endpoint does not exist; locally, run
        <code>npm run dev:evaluation</code>.
      </div>
    {:else if reports.length === 0}
      <div class="state">No participant has logged anything yet.</div>
    {:else if view.kind === "participant" && !current}
      <div class="state">No log for a participant named {view.id}.</div>
    {:else if current}
      {#key current.id}
        <ParticipantReport report={current} />
      {/key}
    {:else}
      <AggregateReport {aggregate} {reports} />
    {/if}
  </main>
</div>
