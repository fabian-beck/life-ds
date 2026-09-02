<script>
  /*
   * A distribution as a strip of dots on one axis, the median marked with a
   * hairline. Used for durations; hovering a dot names whose it is.
   */
  import { formatDuration } from "./format.js";

  const { values = [], median = null, width = 600 } = $props();

  const LEFT = 12;
  const RIGHT = 12;
  const HEIGHT = 70;
  const DOT_Y = 26;

  const maxValue = $derived(
    Math.max(60_000, ...values.map((entry) => entry.value || 0))
  );
  const plotWidth = $derived(width - LEFT - RIGHT);

  function x(ms) {
    return LEFT + (ms / maxValue) * plotWidth;
  }

  const ticks = $derived.by(() => {
    const minutes = maxValue / 60_000;
    const step =
      minutes <= 5
        ? 1
        : minutes <= 15
          ? 2
          : minutes <= 40
            ? 5
            : minutes <= 120
              ? 15
              : 30;
    const result = [];
    for (let m = 0; m * 60_000 <= maxValue; m += step) result.push(m);
    return result;
  });

  // Dots that would overlap are stacked upward, so a cluster stays countable.
  const placed = $derived.by(() => {
    const sorted = [...values].sort((a, b) => a.value - b.value);
    const columns = [];
    return sorted.map((entry) => {
      const cx = x(entry.value);
      let level = 0;
      while (columns[level] !== undefined && cx - columns[level] < 10)
        level += 1;
      columns[level] = cx;
      for (let i = level + 1; i < columns.length; i += 1) {
        if (columns[i] !== undefined && cx - columns[i] >= 10)
          columns[i] = undefined;
      }
      return { ...entry, cx, cy: DOT_Y - level * 10 };
    });
  });
</script>

<svg
  class="chart"
  viewBox="0 0 {width} {HEIGHT}"
  {width}
  height={HEIGHT}
  role="img"
  aria-label="Distribution"
>
  <line
    class="axis"
    x1={LEFT}
    x2={width - RIGHT}
    y1={DOT_Y + 12}
    y2={DOT_Y + 12}
  />
  {#each ticks as minute (minute)}
    <line
      class="tickmark"
      x1={x(minute * 60_000)}
      x2={x(minute * 60_000)}
      y1={DOT_Y + 12}
      y2={DOT_Y + 16}
    />
    <text class="tick" x={x(minute * 60_000)} y={DOT_Y + 30}>{minute} min</text>
  {/each}
  {#if median !== null}
    <line
      class="median"
      x1={x(median)}
      x2={x(median)}
      y1={DOT_Y - 22}
      y2={DOT_Y + 12}
    />
    <text class="median-label" x={x(median) + 5} y={DOT_Y - 14}
      >median {formatDuration(median)}</text
    >
  {/if}
  {#each placed as entry (entry.label)}
    <circle class="dot" cx={entry.cx} cy={entry.cy} r="4">
      <title>{entry.label}: {formatDuration(entry.value)}</title>
    </circle>
  {/each}
</svg>

<style>
  .axis {
    stroke: var(--rule);
    stroke-width: 1;
  }

  .tickmark {
    stroke: var(--rule);
    stroke-width: 1;
  }

  .tick {
    fill: var(--muted);
    font-family: var(--sans);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    text-anchor: middle;
  }

  .dot {
    fill: var(--series-1);
    stroke: var(--paper);
    stroke-width: 2;
  }

  .median {
    stroke: var(--ink);
    stroke-width: 1;
  }

  .median-label {
    fill: var(--ink);
    font-family: var(--sans);
    font-size: 11px;
  }
</style>
