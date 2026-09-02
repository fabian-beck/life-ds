<script>
  /*
   * One participant's report: their sessions, the stories they read and how
   * far, the collections, the landing page, the controls they used, and the
   * log itself at the end.
   */
  import {
    FEATURES,
    NAVIGATION_CLASSES,
  } from "../../utils/evaluation/analysis.js";
  import {
    browserFamily,
    formatCount,
    formatDateTime,
    formatDuration,
    formatPercent,
    nameFromId,
    platformFamily,
  } from "./format.js";
  import { numberBlocks } from "./numbering.js";
  import ActivityStrip from "./ActivityStrip.svelte";
  import BarChart from "./BarChart.svelte";
  import ColumnChart from "./ColumnChart.svelte";
  import Figure from "./Figure.svelte";
  import RawLog from "./RawLog.svelte";
  import TableBlock from "./TableBlock.svelte";

  const { report } = $props();

  const storyNames = $derived(
    new Map(
      report.stories.map((story) => [
        story.id,
        story.name ?? nameFromId(story.id),
      ])
    )
  );
  const metaTitles = $derived(
    new Map(
      report.metas.map((meta) => [meta.id, meta.title ?? nameFromId(meta.id)])
    )
  );

  function segmentName(segment) {
    if (segment.kind === "story")
      return storyNames.get(segment.id) ?? nameFromId(segment.id);
    if (segment.kind === "meta")
      return metaTitles.get(segment.id) ?? nameFromId(segment.id);
    if (segment.kind === "landing") return "Landing page";
    return "Other";
  }

  const stripSessions = $derived(
    report.sessions.map((session) => ({
      id: session.id,
      start: session.start,
      duration: session.duration,
      segments: report.segments
        .filter((segment) => segment.session === session.id)
        .map((segment) => ({ ...segment, name: segmentName(segment) })),
    }))
  );

  const longestStory = $derived(report.stories[0] ?? null);
  const dwellRows = $derived.by(() => {
    if (!longestStory) return [];
    const byIndex = new Map(
      longestStory.slideDwell.map((entry) => [entry.index, entry])
    );
    const total = longestStory.slidesTotal ?? longestStory.slideDwell.length;
    return Array.from({ length: total }, (_, index) => {
      const entry = byIndex.get(index);
      return {
        index,
        type: entry?.type ?? "event",
        ms: entry?.ms ?? 0,
      };
    });
  });

  const navigationRows = $derived(
    NAVIGATION_CLASSES.map((cls) => ({
      label: cls.label,
      value: report.navigation.get(cls.key) ?? 0,
    })).filter((row) => row.value > 0)
  );

  const featureRows = $derived(
    FEATURES.map((feature) => ({
      label: feature.label,
      group: feature.group,
      value: report.features.get(feature.key) ?? 0,
    }))
  );

  const hasMetas = $derived(report.metas.length > 0);
  const hasErrors = $derived(report.errors.length > 0);

  const figures = $derived(
    numberBlocks([
      ["activity", true],
      ["dwell", longestStory !== null && dwellRows.length > 0],
      ["navigation", navigationRows.length > 0],
      ["features", true],
    ])
  );
  const tables = $derived(
    numberBlocks([
      ["sessions", true],
      ["stories", report.stories.length > 0],
      ["metas", hasMetas],
      ["landing", true],
      ["errors", hasErrors],
    ])
  );

  const env = $derived(report.environment);
  const device = $derived(
    env.ua
      ? `${browserFamily(env.ua)} on ${platformFamily(env.ua)}, ${env.w}×${env.h}${env.touch ? ", touch" : ""}`
      : "unknown device"
  );

  let section = 0;
  function next() {
    section += 1;
    return section;
  }
  const sections = $derived.by(() => {
    section = 0;
    return {
      sessions: next(),
      stories: next(),
      metas: hasMetas ? next() : null,
      landing: next(),
      features: next(),
      errors: hasErrors ? next() : null,
      log: next(),
    };
  });
</script>

<header class="titleblock">
  <p class="kicker">Life Data Stories · User evaluation · Individual report</p>
  <h1>Participant {report.id}</h1>
  <p class="subtitle">
    What one reader did with the application, session by session, from the
    interaction log recorded under this participant ID.
  </p>
  <div class="meta-row">
    <span class="chip"><b>{report.totals.sessions}</b> sessions</span>
    <span class="chip"
      ><b>{formatDuration(report.totals.duration)}</b> elapsed</span
    >
    <span class="chip"
      ><b>{formatDuration(report.totals.activeDuration)}</b> active</span
    >
    <span class="chip"><b>{report.totals.stories}</b> person stories</span>
    <span class="chip"><b>{report.totals.metas}</b> meta stories</span>
    <span class="chip"><b>{formatCount(report.totals.events)}</b> events</span>
    <span class="chip">{device}</span>
  </div>
</header>

<div class="report">
  <h2 class="sec" id="sessions">
    <span class="secno">{sections.sessions}</span>Sessions
  </h2>
  <p>
    A session is one browser tab; a reload continues it and a new tab starts
    another. Elapsed time runs from the first to the last recorded event, and
    active time leaves out the stretches in which the tab was hidden. The
    participant read in {report.languages.length === 1
      ? "one language"
      : `${report.languages.length} languages`}
    ({report.languages.join(", ") || "—"}) on {device}.
  </p>

  <TableBlock
    n={tables.sessions}
    caption="The participant's sessions, with the views opened in each."
    wide
  >
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Start</th>
          <th class="num">Elapsed</th>
          <th class="num">Active</th>
          <th class="num">Person stories</th>
          <th class="num">Meta stories</th>
          <th class="num">Events</th>
          <th>Viewport</th>
          <th>Language</th>
        </tr>
      </thead>
      <tbody>
        {#each report.sessions as session, i (session.id)}
          <tr>
            <td class="num">{i + 1}</td>
            <td
              >{formatDateTime(session.start)}{session.resumed
                ? " (resumed)"
                : ""}</td
            >
            <td class="num">{formatDuration(session.duration)}</td>
            <td class="num">{formatDuration(session.activeDuration)}</td>
            <td class="num">{session.stories}</td>
            <td class="num">{session.metas}</td>
            <td class="num">{formatCount(session.eventCount)}</td>
            <td
              >{session.environment.w ?? "—"}×{session.environment.h ?? "—"}</td
            >
            <td
              >{session.languages.join(", ") ||
                session.environment.lang ||
                "—"}</td
            >
          </tr>
        {/each}
      </tbody>
    </table>
  </TableBlock>

  <Figure
    n={figures.activity}
    caption="Where each session was spent: the landing page, person stories, and meta stories over the session's own time. Hovering a stretch names the story."
    wide
  >
    <ActivityStrip sessions={stripSessions} />
  </Figure>

  <h2 class="sec" id="stories">
    <span class="secno">{sections.stories}</span>Person stories
  </h2>
  {#if report.stories.length === 0}
    <p>The participant opened no person story.</p>
  {:else}
    <p>
      A story is a strip of slides. Coverage is the share of its slides the
      participant landed on at least once, and a story counts as read to the end
      when its last slide was reached. The depth layer is the report below the
      fold of a landmark event; the count is the number of such layers the
      participant scrolled into.
    </p>
    <TableBlock
      n={tables.stories}
      caption="The person stories opened, ordered by time spent."
      wide
    >
      <table>
        <thead>
          <tr>
            <th>Story</th>
            <th class="num">Visits</th>
            <th class="num">Time</th>
            <th class="num">Slides seen</th>
            <th class="num">Coverage</th>
            <th>To the end</th>
            <th class="num">Depth layers</th>
            <th class="num">Network</th>
            <th class="num">Timeline</th>
            <th class="num">Images</th>
            <th class="num">Annotations</th>
            <th class="num">Date notes</th>
            <th class="num">Person chips</th>
          </tr>
        </thead>
        <tbody>
          {#each report.stories as story (story.id)}
            <tr>
              <td
                >{story.name ?? nameFromId(story.id)}{story.fromMeta
                  ? " (from a meta story)"
                  : ""}</td
              >
              <td class="num">{story.visits}</td>
              <td class="num">{formatDuration(story.duration)}</td>
              <td class="num"
                >{story.slidesVisited.length}{story.slidesTotal
                  ? ` of ${story.slidesTotal}`
                  : ""}</td
              >
              <td class="num">{formatPercent(story.coverage)}</td>
              <td>{story.reachedEnd ? "yes" : "no"}</td>
              <td class="num">{story.depthEntered.length}</td>
              <td class="num">{story.networkOpens}</td>
              <td class="num">{story.timelineExpands}</td>
              <td class="num">{story.images}</td>
              <td class="num">{story.annotations}</td>
              <td class="num">{story.dateNotes}</td>
              <td class="num">{story.personInfos}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </TableBlock>

    {#if figures.dwell}
      <Figure
        n={figures.dwell}
        caption="Time on each slide of the story read longest, {longestStory.name ??
          nameFromId(
            longestStory.id
          )}, in slide order. A missing column is a slide never landed on."
      >
        <ColumnChart rows={dwellRows} />
      </Figure>
    {/if}

    {#if figures.navigation}
      <p>
        Slides can be changed by swiping or scrolling the strip, by the arrow
        buttons, by the keyboard, from the timeline, and from the image gallery.
        The counts below leave out the first slide of every visit, which no
        gesture chose.
      </p>
      <Figure
        n={figures.navigation}
        caption="How the participant moved between slides, by mechanism, across all person stories."
      >
        <BarChart rows={navigationRows} format={formatCount} />
      </Figure>
    {/if}
  {/if}

  {#if hasMetas}
    <h2 class="sec" id="metas">
      <span class="secno">{sections.metas}</span>Meta stories
    </h2>
    <p>
      A meta story is one scrolling document. Scroll depth is the furthest the
      participant scrolled, as a share of the document's height; the sections
      are the parts of it that passed the middle of the screen.
    </p>
    <TableBlock
      n={tables.metas}
      caption="The meta stories opened, ordered by time spent."
      wide
    >
      <table>
        <thead>
          <tr>
            <th>Meta story</th>
            <th class="num">Visits</th>
            <th class="num">Time</th>
            <th class="num">Scroll depth</th>
            <th>Sections reached</th>
            <th class="num">Timeline</th>
            <th class="num">Network</th>
            <th class="num">Map stops</th>
            <th class="num">Figures</th>
            <th class="num">Stories opened</th>
          </tr>
        </thead>
        <tbody>
          {#each report.metas as meta (meta.id)}
            <tr>
              <td>{meta.title ?? nameFromId(meta.id)}</td>
              <td class="num">{meta.visits}</td>
              <td class="num">{formatDuration(meta.duration)}</td>
              <td class="num">{formatPercent(meta.maxProgress)}</td>
              <td>{meta.sections.join(", ") || "—"}</td>
              <td class="num">{meta.timelineActions}</td>
              <td class="num">{meta.networkSelections}</td>
              <td class="num">{meta.mapSteps}</td>
              <td class="num">{meta.images}</td>
              <td class="num">{meta.storiesOpened}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </TableBlock>
  {/if}

  <h2 class="sec" id="landing">
    <span class="secno">{sections.landing}</span>Landing page
  </h2>
  <p>
    The landing page offers four ways into a story: the portrait grid, the
    collection carousel, the search and role filters, and the map of every place
    in the corpus. The participant spent {formatDuration(
      report.landing.duration
    )}
    there in total{report.landing.timeToFirstStory !== null
      ? ` and opened the first story after ${formatDuration(report.landing.timeToFirstStory)}`
      : " and opened no story"}.
  </p>
  <TableBlock
    n={tables.landing}
    caption="Use of the landing page's controls across all sessions."
  >
    <table>
      <tbody>
        <tr
          ><td>Searches</td><td class="num">{report.landing.searches.length}</td
          ><td class="muted"
            >{report.landing.searches.map((q) => `“${q}”`).join(", ")}</td
          ></tr
        >
        <tr
          ><td>Role filters applied</td><td class="num"
            >{report.landing.filterToggles}</td
          ><td></td></tr
        >
        <tr
          ><td>Collection filters applied</td><td class="num"
            >{report.landing.collectionFilters}</td
          ><td></td></tr
        >
        <tr
          ><td>Map shown</td><td class="num">{report.landing.mapShown}</td><td
          ></td></tr
        >
        <tr
          ><td>Carousel controls</td><td class="num"
            >{report.landing.carouselActions}</td
          ><td></td></tr
        >
        <tr
          ><td>Collections explored</td><td class="num"
            >{report.landing.exploreCollections}</td
          ><td></td></tr
        >
        <tr
          ><td>Stories opened from a card</td><td class="num"
            >{report.landing.selections.get("card") ?? 0}</td
          ><td></td></tr
        >
        <tr
          ><td>Stories opened from the carousel</td><td class="num"
            >{report.landing.selections.get("carousel") ?? 0}</td
          ><td></td></tr
        >
        <tr
          ><td>Events opened from the map</td><td class="num"
            >{report.landing.selections.get("map") ?? 0}</td
          ><td></td></tr
        >
      </tbody>
    </table>
  </TableBlock>

  <h2 class="sec" id="features">
    <span class="secno">{sections.features}</span>Controls used
  </h2>
  <p>
    Every control the application offers, and how often the participant used it.
    A zero is a finding too: a control that a reader never reached.
  </p>
  <Figure
    n={figures.features}
    caption="Uses of each control, grouped by the part of the application it belongs to."
  >
    <BarChart rows={featureRows} format={formatCount} labelWidth={220} />
  </Figure>

  {#if hasErrors}
    <h2 class="sec" id="errors">
      <span class="secno">{sections.errors}</span>Errors
    </h2>
    <p>Script errors the browser reported while the participant read.</p>
    <TableBlock n={tables.errors} caption="Script errors, in order." wide>
      <table>
        <thead><tr><th>Time</th><th>Message</th><th>Source</th></tr></thead>
        <tbody>
          {#each report.errors as error, i (i)}
            <tr
              ><td>{formatDateTime(error.t)}</td><td
                ><code>{error.message}</code></td
              ><td><code>{error.source ?? ""}</code></td></tr
            >
          {/each}
        </tbody>
      </table>
    </TableBlock>
  {/if}

  <h2 class="sec" id="log"><span class="secno">{sections.log}</span>The log</h2>
  <p>
    The events every number above was computed from, in the order they were
    recorded. Clicks carry the control under them; keys are the navigation keys
    only; nothing typed is recorded except the search query.
  </p>
  <RawLog events={report.events} participant={report.id} />
</div>
