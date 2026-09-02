<script>
  /*
   * Time spent per slide of one story, in slide order. Event slides carry the
   * series hue; the structural slides — overview, chapter titles, conclusion
   * — recede to gray, so the shape of the reading is the shape of the events.
   * Only the longest dwell is labeled; the rest is on the axis and in the
   * hover.
   */
  const { rows = [], width = 600 } = $props();

  const LEFT = 44;
  const BOTTOM = 26;
  const TOP = 18;
  const HEIGHT = 180;

  const maxValue = $derived(Math.max(1, ...rows.map((row) => row.ms || 0)));
  const plotWidth = $derived(width - LEFT - 8);
  const plotHeight = HEIGHT - TOP - BOTTOM;
  const slot = $derived(rows.length ? plotWidth / rows.length : plotWidth);
  const bar = $derived(Math.min(24, Math.max(3, slot - 2)));
  const maxIndex = $derived(
    rows.reduce(
      (best, row, i) => (row.ms > (rows[best]?.ms ?? -1) ? i : best),
      0
    )
  );

  const yTicks = $derived.by(() => {
    const seconds = maxValue / 1000;
    const step =
      seconds <= 20
        ? 5
        : seconds <= 60
          ? 10
          : seconds <= 180
            ? 30
            : seconds <= 600
              ? 60
              : 300;
    const ticks = [];
    for (let s = 0; s * 1000 <= maxValue; s += step) ticks.push(s);
    return ticks;
  });

  function y(ms) {
    return TOP + plotHeight - (ms / maxValue) * plotHeight;
  }

  function label(seconds) {
    return seconds >= 60 ? `${Math.round(seconds / 60)} min` : `${seconds} s`;
  }

  function columnPath(x, top, w, bottom) {
    const h = bottom - top;
    const r = Math.min(4, w / 2, h / 2);
    if (h <= 0) return "";
    return `M${x},${bottom} v${-(h - r)} a${r},${r} 0 0 1 ${r},${-r} h${w - 2 * r} a${r},${r} 0 0 1 ${r},${r} v${h - r} z`;
  }
</script>

<svg
  class="chart"
  viewBox="0 0 {width} {HEIGHT}"
  {width}
  height={HEIGHT}
  role="img"
  aria-label="Time per slide"
>
  {#each yTicks as tick (tick)}
    <line
      class="grid"
      x1={LEFT}
      x2={width - 8}
      y1={y(tick * 1000)}
      y2={y(tick * 1000)}
    />
    <text class="tick" x={LEFT - 6} y={y(tick * 1000) + 4}>{label(tick)}</text>
  {/each}
  <line
    class="axis"
    x1={LEFT}
    x2={width - 8}
    y1={TOP + plotHeight}
    y2={TOP + plotHeight}
  />
  {#each rows as row, i (row.index)}
    {@const x = LEFT + i * slot + (slot - bar) / 2}
    <path
      class="column {row.type === 'event' ? 'event' : 'structural'}"
      d={columnPath(x, y(row.ms), bar, TOP + plotHeight)}
    >
      <title
        >Slide {row.index + 1} ({row.type}): {Math.round(row.ms / 1000)} s</title
      >
    </path>
    {#if i === maxIndex}
      <text class="value-label" x={x + bar / 2} y={y(row.ms) - 5}
        >{label(Math.round(row.ms / 1000))}</text
      >
    {/if}
    {#if rows.length <= 40 || i % 5 === 0}
      <text class="tick x" x={x + bar / 2} y={HEIGHT - 8}>{row.index + 1}</text>
    {/if}
  {/each}
</svg>
<ul class="legend">
  <li><span class="swatch event"></span>Event slide</li>
  <li>
    <span class="swatch structural"></span>Overview, chapter, or conclusion
  </li>
</ul>

<style>
  .grid {
    stroke: var(--rule-soft);
    stroke-width: 1;
  }

  .axis {
    stroke: var(--rule);
    stroke-width: 1;
  }

  .tick {
    fill: var(--muted);
    font-family: var(--sans);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    text-anchor: end;
  }

  .tick.x {
    text-anchor: middle;
  }

  .column.event,
  .swatch.event {
    fill: var(--series-1);
    background: var(--series-1);
  }

  .column.structural,
  .swatch.structural {
    fill: var(--rule);
    background: var(--rule);
  }

  .value-label {
    fill: var(--ink);
    font-family: var(--sans);
    font-size: 11px;
    text-anchor: middle;
  }
</style>
