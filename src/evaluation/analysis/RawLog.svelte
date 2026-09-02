<script>
  /*
   * The log itself, for the reader who wants to see what a number was made
   * from: every event in order, the details as compact JSON, folded away by
   * default. The download hands the same events out as a JSON file for
   * analysis outside this page.
   */
  import { formatDateTime } from "./format.js";

  const { events = [], participant = "", limit = 3000 } = $props();

  const HIDDEN = new Set(["t", "type", "route"]);

  function details(event) {
    const rest = {};
    for (const [key, value] of Object.entries(event)) {
      if (!HIDDEN.has(key)) rest[key] = value;
    }
    return JSON.stringify(rest);
  }

  let href = $state("");
  $effect(() => {
    const blob = new Blob([JSON.stringify(events)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    href = url;
    return () => URL.revokeObjectURL(url);
  });

  const start = $derived(events[0]?.t ?? 0);
</script>

<details class="raw-log">
  <summary>Event log ({events.length} events)</summary>
  <p class="raw-log-actions">
    <a {href} download="evaluation-{participant}.json">Download as JSON</a>
  </p>
  <div class="table-scroll">
    <table class="raw-log-table">
      <thead>
        <tr>
          <th>Time</th>
          <th>+s</th>
          <th>Type</th>
          <th>Route</th>
          <th>Details</th>
        </tr>
      </thead>
      <tbody>
        {#each events.slice(0, limit) as event, i (i)}
          <tr>
            <td class="num">{formatDateTime(event.t)}</td>
            <td class="num">{((event.t - start) / 1000).toFixed(1)}</td>
            <td><code>{event.type}</code></td>
            <td><code>{event.route ?? ""}</code></td>
            <td class="details"><code>{details(event)}</code></td>
          </tr>
        {/each}
      </tbody>
    </table>
    {#if events.length > limit}
      <p class="raw-log-note">
        The first {limit} of {events.length} events are shown; the download carries
        all of them.
      </p>
    {/if}
  </div>
</details>
