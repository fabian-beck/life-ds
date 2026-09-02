<script>
  /*
   * One row per session, time running left to right on a shared axis, each
   * stretch colored by the kind of view that was open — the three kinds the
   * application has, in the three categorical slots the page reserves for
   * them. A legend names the slots; hovering a stretch names the story.
   */
  import { formatDuration } from "./format.js";

  const { sessions = [], width = 760 } = $props();

  const LABEL = 92;
  const ROW = 26;
  const BAR = 14;
  const AXIS = 22;

  const maxDuration = $derived(
    Math.max(60_000, ...sessions.map((session) => session.duration || 0))
  );
  const plotWidth = $derived(width - LABEL - 12);
  const height = $derived(sessions.length * ROW + AXIS + 8);

  const ticks = $derived.by(() => {
    const minutes = maxDuration / 60_000;
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
    for (let m = 0; m * 60_000 <= maxDuration; m += step) result.push(m);
    return result;
  });

  function x(ms) {
    return LABEL + (ms / maxDuration) * plotWidth;
  }

  const kinds = [
    { key: "landing", label: "Landing page" },
    { key: "story", label: "Person story" },
    { key: "meta", label: "Meta story" },
  ];
</script>

<svg
  class="chart"
  viewBox="0 0 {width} {height}"
  {width}
  {height}
  role="img"
  aria-label="Activity over time per session"
>
  {#each ticks as minute (minute)}
    <line
      class="grid"
      x1={x(minute * 60_000)}
      x2={x(minute * 60_000)}
      y1={0}
      y2={sessions.length * ROW}
    />
    <text class="tick" x={x(minute * 60_000)} y={sessions.length * ROW + 14}
      >{minute} min</text
    >
  {/each}
  {#each sessions as session, i (session.id)}
    <text class="row-label" x={LABEL - 8} y={i * ROW + BAR / 2 + 4}
      >Session {i + 1}</text
    >
    <rect
      class="track"
      x={LABEL}
      y={i * ROW}
      width={(session.duration / maxDuration) * plotWidth}
      height={BAR}
    />
    {#each session.segments as segment (segment.start)}
      {@const start = segment.start - session.start}
      {@const w = Math.max(1, (segment.duration / maxDuration) * plotWidth - 1)}
      <rect
        class="segment {segment.kind}"
        x={x(start)}
        y={i * ROW}
        width={w}
        height={BAR}
      >
        <title
          >{segment.name ?? segment.kind} · {formatDuration(
            segment.duration
          )}</title
        >
      </rect>
    {/each}
  {/each}
</svg>
<ul class="legend">
  {#each kinds as kind (kind.key)}
    <li><span class="swatch {kind.key}"></span>{kind.label}</li>
  {/each}
</ul>

<style>
  .grid {
    stroke: var(--rule-soft);
    stroke-width: 1;
  }

  .tick,
  .row-label {
    fill: var(--muted);
    font-family: var(--sans);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
  }

  .tick {
    text-anchor: middle;
  }

  .row-label {
    fill: var(--ink-2);
    font-size: 12px;
    text-anchor: end;
  }

  .track {
    fill: var(--surface);
  }

  .segment.landing,
  .swatch.landing {
    fill: var(--series-3);
    background: var(--series-3);
  }

  .segment.story,
  .swatch.story {
    fill: var(--series-1);
    background: var(--series-1);
  }

  .segment.meta,
  .swatch.meta {
    fill: var(--series-2);
    background: var(--series-2);
  }

  .segment.other {
    fill: var(--rule);
  }
</style>
