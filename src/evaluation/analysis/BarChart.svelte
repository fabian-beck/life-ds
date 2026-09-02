<script>
  /*
   * Horizontal bars for one measure over named rows, optionally grouped. One
   * hue, since the rows are one series; the value at the tip of every bar,
   * because the rows are few and the number is what the reader came for.
   * Each row also carries a `title` so hovering a bar restates it.
   */
  const {
    rows = [],
    format = (value) => String(value),
    max = null,
    width = 600,
    labelWidth = 200,
  } = $props();

  const ROW = 22;
  const BAR = 14;
  const GROUP_GAP = 18;
  const VALUE_GAP = 6;
  const VALUE_WIDTH = 64;

  const layout = $derived.by(() => {
    const items = [];
    let y = 4;
    let lastGroup = null;
    for (const row of rows) {
      if (row.group && row.group !== lastGroup) {
        if (lastGroup !== null) y += GROUP_GAP;
        items.push({ kind: "group", label: row.group, y: y + 12 });
        y += ROW;
        lastGroup = row.group;
      }
      items.push({ kind: "row", ...row, y });
      y += ROW;
    }
    return { items, height: y + 4 };
  });

  const scaleMax = $derived(
    max ?? Math.max(1, ...rows.map((row) => Number(row.value) || 0))
  );
  const plotWidth = $derived(width - labelWidth - VALUE_WIDTH - VALUE_GAP);

  function barPath(x, y, w, h) {
    const r = Math.min(4, w / 2, h / 2);
    if (w <= 0) return "";
    return `M${x},${y} h${w - r} a${r},${r} 0 0 1 ${r},${r} v${h - 2 * r} a${r},${r} 0 0 1 ${-r},${r} h${-(w - r)} z`;
  }
</script>

<svg
  class="chart"
  viewBox="0 0 {width} {layout.height}"
  {width}
  height={layout.height}
  role="img"
  aria-label="Bar chart"
>
  <line
    class="axis"
    x1={labelWidth}
    x2={labelWidth}
    y1={0}
    y2={layout.height}
  />
  {#each layout.items as item (item.kind + item.label + item.y)}
    {#if item.kind === "group"}
      <text class="group-label" x={0} y={item.y}>{item.label}</text>
    {:else}
      {@const w = ((Number(item.value) || 0) / scaleMax) * plotWidth}
      <text class="row-label" x={labelWidth - 8} y={item.y + BAR / 2 + 4}
        >{item.label}</text
      >
      <path class="bar" d={barPath(labelWidth, item.y, w, BAR)}>
        <title>{item.title ?? `${item.label}: ${format(item.value)}`}</title>
      </path>
      <text
        class="value-label"
        x={labelWidth + w + VALUE_GAP}
        y={item.y + BAR / 2 + 4}>{format(item.value)}</text
      >
    {/if}
  {/each}
</svg>

<style>
  .axis {
    stroke: var(--rule);
    stroke-width: 1;
  }

  .bar {
    fill: var(--series-1);
  }

  .row-label {
    fill: var(--ink-2);
    font-family: var(--sans);
    font-size: 12px;
    text-anchor: end;
  }

  .group-label {
    fill: var(--muted);
    font-family: var(--sans);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .value-label {
    fill: var(--ink);
    font-family: var(--sans);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
  }
</style>
