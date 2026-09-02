<script>
  /*
   * The share of story visits that reached each tenth of a story: a line, its
   * points ringed in the surface color, the endpoint labeled. One series, so
   * the title names it and no legend is drawn.
   */
  const { steps = [], width = 520 } = $props();

  const LEFT = 44;
  const RIGHT = 40;
  const TOP = 14;
  const BOTTOM = 28;
  const HEIGHT = 200;

  const plotWidth = $derived(width - LEFT - RIGHT);
  const plotHeight = HEIGHT - TOP - BOTTOM;

  function x(position) {
    return LEFT + position * plotWidth;
  }

  function y(share) {
    return TOP + plotHeight - share * plotHeight;
  }

  const path = $derived(
    steps
      .map(
        (step, i) =>
          `${i === 0 ? "M" : "L"}${x(step.position)},${y(step.share)}`
      )
      .join(" ")
  );
  const last = $derived(steps[steps.length - 1] ?? null);
</script>

<svg
  class="chart"
  viewBox="0 0 {width} {HEIGHT}"
  {width}
  height={HEIGHT}
  role="img"
  aria-label="Share of visits reaching each part of a story"
>
  {#each [0, 0.25, 0.5, 0.75, 1] as tick (tick)}
    <line class="grid" x1={LEFT} x2={width - RIGHT} y1={y(tick)} y2={y(tick)} />
    <text class="tick" x={LEFT - 6} y={y(tick) + 4}
      >{Math.round(tick * 100)}%</text
    >
  {/each}
  {#each [0, 0.2, 0.4, 0.6, 0.8, 1] as tick (tick)}
    <text class="tick x" x={x(tick)} y={HEIGHT - 8}
      >{Math.round(tick * 100)}%</text
    >
  {/each}
  <line
    class="axis"
    x1={LEFT}
    x2={width - RIGHT}
    y1={TOP + plotHeight}
    y2={TOP + plotHeight}
  />
  <path class="line" d={path} />
  {#each steps as step (step.position)}
    <circle class="dot" cx={x(step.position)} cy={y(step.share)} r="4">
      <title
        >{Math.round(step.position * 100)}% of the story: {Math.round(
          step.share * 100
        )}% of visits</title
      >
    </circle>
  {/each}
  {#if last}
    <text class="value-label" x={x(last.position) + 8} y={y(last.share) + 4}
      >{Math.round(last.share * 100)}%</text
    >
  {/if}
  <text class="axis-title" x={LEFT + plotWidth / 2} y={HEIGHT + 0}></text>
</svg>

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

  .line {
    fill: none;
    stroke: var(--series-1);
    stroke-width: 2;
    stroke-linejoin: round;
    stroke-linecap: round;
  }

  .dot {
    fill: var(--series-1);
    stroke: var(--paper);
    stroke-width: 2;
  }

  .value-label {
    fill: var(--ink);
    font-family: var(--sans);
    font-size: 11px;
  }
</style>
