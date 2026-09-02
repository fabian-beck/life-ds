<script>
  /*
   * The report across participants: who took part, how long they stayed, how
   * far into the stories they read, how they moved, and which controls found
   * use. Every table links a participant to their own report.
   */
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
  import BarChart from "./BarChart.svelte";
  import DotStrip from "./DotStrip.svelte";
  import Figure from "./Figure.svelte";
  import StepCurve from "./StepCurve.svelte";
  import TableBlock from "./TableBlock.svelte";

  const { aggregate, reports } = $props();

  const durationDots = $derived(
    reports.map((report) => ({
      label: report.id,
      value: report.totals.duration,
    }))
  );

  const slideTypeLabels = {
    overview: "Overview",
    chapter: "Chapter title",
    event: "Event",
    conclusion: "Conclusion",
    unknown: "Unknown",
  };
  const slideTypeRows = $derived(
    aggregate.slideTypeDwell.map((entry) => ({
      label: slideTypeLabels[entry.type] ?? entry.type,
      value: entry.median ?? 0,
      title: `${slideTypeLabels[entry.type] ?? entry.type}: median ${formatDuration(entry.median)} over ${entry.count} slide views`,
    }))
  );

  const navigationRows = $derived(
    aggregate.navigation.map((cls) => ({
      label: cls.label,
      value: cls.share,
      title: `${cls.label}: ${formatCount(cls.count)} slide changes, ${formatPercent(cls.share)}`,
    }))
  );

  const featureRows = $derived(
    aggregate.features.map((feature) => ({
      label: feature.label,
      group: feature.group,
      value: feature.share,
      title: `${feature.label}: ${feature.users} of ${aggregate.participants} participants, ${feature.uses} uses`,
    }))
  );

  const hasStories = $derived(aggregate.stories.length > 0);
  const hasMetas = $derived(aggregate.metas.length > 0);
  const hasErrors = $derived(aggregate.errors.length > 0);

  const figures = $derived(
    numberBlocks([
      ["durations", true],
      ["dropoff", hasStories && aggregate.storyVisits > 0],
      ["slideTypes", slideTypeRows.length > 0],
      ["navigation", navigationRows.length > 0],
      ["features", true],
    ])
  );
  const tables = $derived(
    numberBlocks([
      ["participants", true],
      ["stories", hasStories],
      ["features", true],
      ["metas", hasMetas],
      ["landing", true],
      ["errors", hasErrors],
    ])
  );

  let section = 0;
  function next() {
    section += 1;
    return section;
  }
  const sections = $derived.by(() => {
    section = 0;
    return {
      participants: next(),
      stories: next(),
      navigation: navigationRows.length > 0 ? next() : null,
      features: next(),
      metas: hasMetas ? next() : null,
      landing: next(),
      errors: hasErrors ? next() : null,
    };
  });

  const widthRange = $derived(
    aggregate.widths.length
      ? `${Math.min(...aggregate.widths)}–${Math.max(...aggregate.widths)} px`
      : "—"
  );
</script>

<header class="titleblock">
  <p class="kicker">Life Data Stories · User evaluation · Aggregate report</p>
  <h1>All participants</h1>
  <p class="subtitle">
    What the readers of the evaluation deployment did with the application,
    computed from every interaction log recorded so far.
  </p>
  <div class="meta-row">
    <span class="chip"><b>{aggregate.participants}</b> participants</span>
    <span class="chip"><b>{aggregate.sessions}</b> sessions</span>
    <span class="chip"
      ><b>{formatDuration(aggregate.medianDuration)}</b> median time per participant</span
    >
    <span class="chip"><b>{aggregate.storyVisits}</b> story visits</span>
    <span class="chip"><b>{formatCount(aggregate.events)}</b> events</span>
  </div>
</header>

<div class="report">
  <h2 class="sec" id="participants">
    <span class="secno">{sections.participants}</span>Participants and sessions
  </h2>
  <p>
    A participant is an ID entered at the gate; a session is one browser tab
    under it. Of the {aggregate.participants} participants, {aggregate.touch} read
    on a touch device and {aggregate.pointer} with a pointer, at viewport widths of
    {widthRange}. Elapsed time runs from a session's first to its last event;
    active time leaves out the stretches in which the tab was hidden.
  </p>
  <TableBlock
    n={tables.participants}
    caption="Every participant, with their sessions and what they opened. The ID opens the participant's own report."
    wide
  >
    <table>
      <thead>
        <tr>
          <th>Participant</th>
          <th>First seen</th>
          <th class="num">Sessions</th>
          <th class="num">Elapsed</th>
          <th class="num">Active</th>
          <th class="num">Person stories</th>
          <th class="num">Meta stories</th>
          <th class="num">Events</th>
          <th>Device</th>
          <th>Viewport</th>
          <th>Language</th>
        </tr>
      </thead>
      <tbody>
        {#each reports as report (report.id)}
          <tr>
            <td
              ><a href="#/participant/{encodeURIComponent(report.id)}"
                >{report.id}</a
              ></td
            >
            <td>{formatDateTime(report.sessions[0]?.start)}</td>
            <td class="num">{report.totals.sessions}</td>
            <td class="num">{formatDuration(report.totals.duration)}</td>
            <td class="num">{formatDuration(report.totals.activeDuration)}</td>
            <td class="num">{report.totals.stories}</td>
            <td class="num">{report.totals.metas}</td>
            <td class="num">{formatCount(report.totals.events)}</td>
            <td
              >{browserFamily(report.environment.ua)}, {platformFamily(
                report.environment.ua
              )}{report.environment.touch ? ", touch" : ""}</td
            >
            <td>{report.environment.w ?? "—"}×{report.environment.h ?? "—"}</td>
            <td>{report.languages.join(", ") || "—"}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </TableBlock>

  <Figure
    n={figures.durations}
    caption="Elapsed time per participant across all their sessions, one dot each, with the median marked."
  >
    <DotStrip values={durationDots} median={aggregate.medianDuration} />
  </Figure>

  <h2 class="sec" id="stories">
    <span class="secno">{sections.stories}</span>Reading person stories
  </h2>
  {#if !hasStories}
    <p>No participant opened a person story.</p>
  {:else}
    <p>
      Across {aggregate.storyVisits} visits to person stories, the median visit lasted
      {formatDuration(aggregate.medianVisitDuration)} and covered {formatPercent(
        aggregate.medianCoverage
      )}
      of the story's slides; {formatPercent(aggregate.completionRate)} of visits reached
      the last slide. Coverage is the share of a story's slides landed on at least
      once in a visit. A reader counts for a story once, however many times they opened
      it.
    </p>
    <TableBlock
      n={tables.stories}
      caption="The person stories opened, by how many participants read them. Medians are over participants."
      wide
    >
      <table>
        <thead>
          <tr>
            <th>Story</th>
            <th class="num">Readers</th>
            <th class="num">Visits</th>
            <th class="num">Median time</th>
            <th class="num">Median coverage</th>
            <th class="num">Read to the end</th>
            <th class="num">Opened a depth layer</th>
            <th class="num">Opened the network</th>
          </tr>
        </thead>
        <tbody>
          {#each aggregate.stories as story (story.id)}
            <tr>
              <td>{story.name ?? nameFromId(story.id)}</td>
              <td class="num">{story.readers}</td>
              <td class="num">{story.visits}</td>
              <td class="num">{formatDuration(story.medianDuration)}</td>
              <td class="num">{formatPercent(story.medianCoverage)}</td>
              <td class="num">{story.completions} of {story.readers}</td>
              <td class="num">{story.depthReaders} of {story.readers}</td>
              <td class="num">{story.networkReaders} of {story.readers}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </TableBlock>

    {#if figures.dropoff}
      <Figure
        n={figures.dropoff}
        caption="Drop-off: the share of story visits that reached at least each tenth of the story, by the furthest slide reached."
      >
        <StepCurve steps={aggregate.dropOff} />
      </Figure>
    {/if}

    {#if figures.slideTypes}
      <p>
        A story is made of four kinds of slide: the overview that opens it, the
        chapter titles that pace it, the events, and the conclusion. The time a
        slide holds a reader differs by kind.
      </p>
      <Figure
        n={figures.slideTypes}
        caption="Median time on a slide, by the kind of slide, over every slide view in every visit."
      >
        <BarChart
          rows={slideTypeRows}
          format={formatDuration}
          labelWidth={140}
        />
      </Figure>
    {/if}
  {/if}

  {#if sections.navigation}
    <h2 class="sec" id="navigation">
      <span class="secno">{sections.navigation}</span>Moving between slides
    </h2>
    <p>
      Slides can be changed by swiping or scrolling the strip, by the arrow
      buttons, by the keyboard, from the timeline, and from the image gallery.
      Of {formatCount(aggregate.navigationTotal)} slide changes, leaving out the first
      slide of every visit, the shares by mechanism were as follows.
    </p>
    <Figure
      n={figures.navigation}
      caption="Share of slide changes by the mechanism that made them, across all participants and stories."
    >
      <BarChart
        rows={navigationRows}
        format={formatPercent}
        max={1}
        labelWidth={150}
      />
    </Figure>
  {/if}

  <h2 class="sec" id="features">
    <span class="secno">{sections.features}</span>Adoption of controls
  </h2>
  <p>
    Every control the application offers, and the share of participants who used
    it at least once. A control nobody reached is a finding about its visibility
    as much as about its use.
  </p>
  <Figure
    n={figures.features}
    caption="Share of participants who used each control at least once, grouped by the part of the application it belongs to."
  >
    <BarChart
      rows={featureRows}
      format={formatPercent}
      max={1}
      labelWidth={220}
    />
  </Figure>
  <TableBlock
    n={tables.features}
    caption="The same controls, with the number of participants and the total number of uses."
  >
    <table>
      <thead>
        <tr
          ><th>Control</th><th>Part</th><th class="num">Participants</th><th
            class="num">Share</th
          ><th class="num">Uses</th></tr
        >
      </thead>
      <tbody>
        {#each aggregate.features as feature (feature.key)}
          <tr>
            <td>{feature.label}</td>
            <td class="muted">{feature.group}</td>
            <td class="num">{feature.users}</td>
            <td class="num">{formatPercent(feature.share)}</td>
            <td class="num">{formatCount(feature.uses)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </TableBlock>

  {#if hasMetas}
    <h2 class="sec" id="metas">
      <span class="secno">{sections.metas}</span>Meta stories
    </h2>
    <p>
      A meta story is one scrolling document with a timeline, a network, and a
      map inside it. Scroll depth is the furthest a participant scrolled, as a
      share of the document's height.
    </p>
    <TableBlock
      n={tables.metas}
      caption="The meta stories opened, by how many participants read them."
      wide
    >
      <table>
        <thead>
          <tr>
            <th>Meta story</th>
            <th class="num">Readers</th>
            <th class="num">Visits</th>
            <th class="num">Median time</th>
            <th class="num">Median scroll depth</th>
            <th class="num">Used the timeline</th>
            <th class="num">Used the network</th>
            <th class="num">Reached the map</th>
            <th class="num">Stories opened from it</th>
          </tr>
        </thead>
        <tbody>
          {#each aggregate.metas as meta (meta.id)}
            <tr>
              <td>{meta.title ?? nameFromId(meta.id)}</td>
              <td class="num">{meta.readers}</td>
              <td class="num">{meta.visits}</td>
              <td class="num">{formatDuration(meta.medianDuration)}</td>
              <td class="num">{formatPercent(meta.medianProgress)}</td>
              <td class="num">{meta.timelineUsers} of {meta.readers}</td>
              <td class="num">{meta.networkUsers} of {meta.readers}</td>
              <td class="num">{meta.mapUsers} of {meta.readers}</td>
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
    collection carousel, the search and role filters, and the map. The median
    participant opened the first story
    {aggregate.landing.medianTimeToFirstStory !== null
      ? `after ${formatDuration(aggregate.landing.medianTimeToFirstStory)}`
      : "never"}.
  </p>
  <TableBlock
    n={tables.landing}
    caption="Use of the landing page's ways in, across participants."
  >
    <table>
      <tbody>
        <tr
          ><td>Participants who searched</td><td class="num"
            >{aggregate.landing.searchUsers} of {aggregate.participants}</td
          ></tr
        >
        <tr
          ><td>Participants who filtered by role or collection</td><td
            class="num"
            >{aggregate.landing.filterUsers} of {aggregate.participants}</td
          ></tr
        >
        <tr
          ><td>Participants who opened the map</td><td class="num"
            >{aggregate.landing.mapUsers} of {aggregate.participants}</td
          ></tr
        >
        <tr
          ><td>Stories opened from a card</td><td class="num"
            >{aggregate.landing.selections.get("card") ?? 0}</td
          ></tr
        >
        <tr
          ><td>Stories opened from the carousel</td><td class="num"
            >{aggregate.landing.selections.get("carousel") ?? 0}</td
          ></tr
        >
        <tr
          ><td>Events opened from the map</td><td class="num"
            >{aggregate.landing.selections.get("map") ?? 0}</td
          ></tr
        >
      </tbody>
    </table>
  </TableBlock>

  {#if hasErrors}
    <h2 class="sec" id="errors">
      <span class="secno">{sections.errors}</span>Errors
    </h2>
    <p>Script errors the participants' browsers reported while they read.</p>
    <TableBlock
      n={tables.errors}
      caption="Script errors, in order, with the participant they happened to."
      wide
    >
      <table>
        <thead
          ><tr
            ><th>Participant</th><th>Time</th><th>Message</th><th>Source</th
            ></tr
          ></thead
        >
        <tbody>
          {#each aggregate.errors as error, i (i)}
            <tr>
              <td
                ><a href="#/participant/{encodeURIComponent(error.participant)}"
                  >{error.participant}</a
                ></td
              >
              <td>{formatDateTime(error.t)}</td>
              <td><code>{error.message}</code></td>
              <td><code>{error.source ?? ""}</code></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </TableBlock>
  {/if}
</div>
