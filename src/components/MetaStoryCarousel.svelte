<script>
  import { _ } from "../stores/language";
  import { displayName } from "../utils/helpers.js";
  import { extractYear } from "../utils/story/dates.js";
  import { getThumbnailUrl } from "../utils/story/images.js";
  import { logEvent } from "../evaluation/log.js";

  export let metaStories = [];
  export let persons = [];
  export let onSelectPerson = () => {};
  export let onFilterByMetaStory = () => {};
  export let onExploreMetaStory = () => {};

  let currentSlide = 0;
  let autoplayInterval;
  let carouselElement;
  let sectionElement;
  let isDragging = false;
  let isHovered = false;
  let startX = 0;
  let scrollLeft = 0;
  let touchStartX = 0;
  let touchDeltaX = 0;
  let isPaused = false;
  let resumeTimeout;
  let resumeTimerActive = false;
  let timerKey = 0;

  const AUTOPLAY_INTERVAL = 5000;
  const RESUME_DELAY = 10000;

  // An explicit stop stays stopped. The ten-second resume timer below belongs
  // to the incidental pause that hover and focus arm — a reader who presses
  // the button has asked for the motion to end, and undoing that for them is
  // what makes the control fail to be one (WCAG 2.2.2).
  let autoplayStopped = false;

  // A full-bleed panel of portraits sliding every five seconds on the entry
  // page is exactly the content this preference exists to suppress.
  const prefersReducedMotion =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  // Auto-advance every 5 seconds
  function startAutoplay() {
    if (autoplayStopped || isHovered || isDragging) {
      return;
    }
    stopAutoplay();
    cancelResumeTimer();
    isPaused = false;
    autoplayInterval = setInterval(() => {
      if (!isDragging && !isHovered) {
        nextSlide();
      }
    }, AUTOPLAY_INTERVAL);
  }

  function stopAutoplay() {
    if (autoplayInterval) {
      clearInterval(autoplayInterval);
      autoplayInterval = null;
    }
  }

  function cancelResumeTimer() {
    if (resumeTimeout) {
      clearTimeout(resumeTimeout);
      resumeTimeout = null;
    }
    resumeTimerActive = false;
  }

  function pauseWithResumeTimer() {
    stopAutoplay();
    cancelResumeTimer();
    isPaused = true;
    // Nothing to resume from: the reader already stopped it themselves.
    if (autoplayStopped) return;
    resumeTimerActive = true;
    timerKey += 1;
    resumeTimeout = setTimeout(() => {
      resumeTimerActive = false;
      startAutoplay();
    }, RESUME_DELAY);
  }

  function toggleAutoplay() {
    if (autoplayStopped) {
      autoplayStopped = false;
      // Pressing play is an explicit request, so it also clears the incidental
      // hover/focus pause the press itself just armed by moving focus in here.
      isHovered = false;
      startAutoplay();
    } else {
      autoplayStopped = true;
      stopAutoplay();
      cancelResumeTimer();
      isPaused = true;
    }
  }

  function nextSlide() {
    currentSlide = (currentSlide + 1) % metaStories.length;
  }

  function prevSlide() {
    currentSlide = (currentSlide - 1 + metaStories.length) % metaStories.length;
  }

  function handlePrevClick() {
    prevSlide();
    pauseWithResumeTimer();
    logEvent("landing.carousel", { action: "prev", index: currentSlide });
  }

  function handleNextClick() {
    nextSlide();
    pauseWithResumeTimer();
    logEvent("landing.carousel", { action: "next", index: currentSlide });
  }

  function goToSlide(index) {
    currentSlide = index;
    pauseWithResumeTimer();
    logEvent("landing.carousel", { action: "goto", index });
  }

  function handleMouseDown(e) {
    isDragging = true;
    startX = e.pageX - carouselElement.offsetLeft;
    scrollLeft = carouselElement.scrollLeft;
    carouselElement.style.cursor = "grabbing";
    stopAutoplay();
  }

  function handleMouseUp() {
    if (!isDragging) return;
    isDragging = false;
    carouselElement.style.cursor = "grab";
    // Autoplay is not resumed here; the section's handleMouseLeave resumes it
    // when the mouse truly leaves.
  }

  function handleMouseMove(e) {
    if (!isDragging) return;
    e.preventDefault();
    const x = e.pageX - carouselElement.offsetLeft;
    const walk = (x - startX) * 2;
    carouselElement.scrollLeft = scrollLeft - walk;
  }

  const SWIPE_THRESHOLD = 50; // Minimum pixels to trigger a swipe

  function handleTouchStart(e) {
    isDragging = true;
    isPaused = true;
    touchStartX = e.touches[0].clientX;
    touchDeltaX = 0;
    stopAutoplay();
    cancelResumeTimer();
  }

  function handleTouchEnd() {
    if (!isDragging) return;
    isDragging = false;

    // Determine swipe direction based on delta
    if (Math.abs(touchDeltaX) >= SWIPE_THRESHOLD) {
      if (touchDeltaX > 0) {
        // Swiped right -> go to previous slide
        prevSlide();
      } else {
        // Swiped left -> go to next slide
        nextSlide();
      }
    }

    // Reset touch tracking
    touchStartX = 0;
    touchDeltaX = 0;

    // Touch devices don't have hover, so use resume timer after touch ends
    pauseWithResumeTimer();
  }

  function handleTouchMove(e) {
    if (!isDragging) return;
    touchDeltaX = e.touches[0].clientX - touchStartX;
  }

  function handleMouseEnter(e) {
    if (isHovered) return;
    // Don't treat touch events as hover to avoid stuck states on mobile
    if (e.pointerType === "touch") return;
    // Ignore internal transitions within the carousel
    if (
      sectionElement &&
      e?.relatedTarget &&
      sectionElement.contains(e.relatedTarget)
    )
      return;
    isHovered = true;

    // Pause autoplay with resume timer as fallback to prevent stuck states
    pauseWithResumeTimer();
  }

  function handleMouseLeave(e) {
    // Ignore internal transitions within the carousel
    if (
      sectionElement &&
      e?.relatedTarget &&
      sectionElement.contains(e.relatedTarget)
    )
      return;
    if (!isHovered) return;
    isHovered = false;

    // Only resume if we are not dragging, and never against an explicit stop
    if (!isDragging && !autoplayStopped) {
      isPaused = false;
      startAutoplay();
    }
  }

  // Shrink the title when it is long or contains a very long single word so it
  // neither overflows the slide (clipped word) nor grows tall enough to cover
  // the portraits behind it. The returned scale multiplies the base font size
  // via the --title-scale CSS custom property.
  const TITLE_TOTAL_LIMIT = 22; // chars that fit comfortably at full size
  const TITLE_WORD_LIMIT = 11; // longest single word that fits at full size
  const TITLE_MIN_SCALE = 0.62; // keep the title readable

  function getTitleScale(title) {
    if (!title) return 1;
    const words = title.split(/\s+/).filter(Boolean);
    const longestWord = words.reduce((max, w) => Math.max(max, w.length), 0);
    const totalLength = title.length;
    const lengthScale =
      totalLength > TITLE_TOTAL_LIMIT ? TITLE_TOTAL_LIMIT / totalLength : 1;
    const wordScale =
      longestWord > TITLE_WORD_LIMIT ? TITLE_WORD_LIMIT / longestWord : 1;
    return Math.max(Math.min(lengthScale, wordScale), TITLE_MIN_SCALE);
  }

  function getPersonsForMetaStory(metaStory) {
    if (!metaStory?.person_ids) return [];

    // Remove duplicates from person_ids first
    const uniquePersonIds = [...new Set(metaStory.person_ids)];

    const personsForStory = uniquePersonIds
      .map((id) => persons.find((p) => p.id === id))
      .filter(Boolean)
      .sort((a, b) => {
        // Birth years via the shared parser (handles BCE and unpadded years);
        // people without a parseable date sort last instead of shuffling.
        const yearOf = (person) => {
          const year = extractYear(person.birthDate);
          return Number.isFinite(year) ? year : Infinity;
        };
        return yearOf(a) - yearOf(b);
      });

    // If more than 6 people, randomly select 6 while maintaining temporal order
    if (personsForStory.length > 6) {
      // Randomly select 6 indices
      const indices = [];
      while (indices.length < 6) {
        const randomIndex = Math.floor(Math.random() * personsForStory.length);
        if (!indices.includes(randomIndex)) {
          indices.push(randomIndex);
        }
      }
      // Sort indices to maintain temporal order, then map to persons
      return indices.sort((a, b) => a - b).map((i) => personsForStory[i]);
    }

    return personsForStory;
  }

  // Start autoplay on mount
  import { onMount, onDestroy } from "svelte";

  onMount(() => {
    if (prefersReducedMotion) {
      autoplayStopped = true;
      isPaused = true;
      return;
    }
    startAutoplay();
  });

  onDestroy(() => {
    stopAutoplay();
    cancelResumeTimer();
  });

  $: if (metaStories.length === 0) {
    stopAutoplay();
  } else if (
    metaStories.length > 0 &&
    !autoplayInterval &&
    !isPaused &&
    !isDragging &&
    !isHovered
  ) {
    // Start autoplay when metaStories becomes populated and not interacting
    startAutoplay();
  }
</script>

{#if metaStories.length > 0}
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- Keyboard users get the same autoplay pause via focusin/focusout, which
       bubble from the cards the way mouseover/mouseout do. on:focus/on:blur,
       which the rule asks for, do not bubble and would never fire on this
       non-focusable section. -->
  <!-- svelte-ignore a11y-mouse-events-have-key-events -->
  <section
    class="meta-story-carousel"
    bind:this={sectionElement}
    on:mouseover={handleMouseEnter}
    on:mouseout={handleMouseLeave}
    on:focusin={handleMouseEnter}
    on:focusout={handleMouseLeave}
  >
    <div class="carousel-container">
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <div
        class="carousel-track"
        bind:this={carouselElement}
        on:mousedown={handleMouseDown}
        on:mouseup={handleMouseUp}
        on:mouseleave={handleMouseUp}
        on:mousemove={handleMouseMove}
        on:touchstart={handleTouchStart}
        on:touchend={handleTouchEnd}
        on:touchmove={handleTouchMove}
        style="transform: translateX(-{currentSlide * 100}%)"
      >
        {#each metaStories as metaStory, index (metaStory.id)}
          {@const storyPersons = getPersonsForMetaStory(metaStory)}
          <div
            class="carousel-slide"
            class:active={index === currentSlide}
            inert={index !== currentSlide}
            aria-hidden={index !== currentSlide}
          >
            {#if storyPersons.length > 0}
              <div class="portrait-background">
                {#each storyPersons as person (person.id)}
                  <button
                    class="portrait-column"
                    on:click={(event) =>
                      onSelectPerson(person.id, event.currentTarget)}
                    data-focus-id={`carousel-person-${person.id}`}
                    aria-label={$_("meta_story.people_open_story", {
                      name: displayName(person.name),
                    })}
                  >
                    <span class="portrait-clip">
                      {#if person?.portrait}
                        <img
                          src={getThumbnailUrl(person.portrait, 300)}
                          srcset={`${getThumbnailUrl(person.portrait, 300)} 266w, ${getThumbnailUrl(person.portrait, 600)} 682w`}
                          sizes="170px"
                          alt={person.portrait.alt ??
                            `Portrait of ${displayName(person.name)}`}
                          loading="lazy"
                          decoding="async"
                        />
                      {/if}
                    </span>
                    <!-- The button's aria-label already announces the name,
                         so the visible caption is hidden from assistive
                         technology to avoid a double reading. -->
                    <span class="portrait-name" aria-hidden="true"
                      >{displayName(person.name)}</span
                    >
                  </button>
                {/each}
              </div>
            {/if}

            <div class="slide-content">
              <div class="slide-header">
                <button
                  class="title-row"
                  on:click={(event) =>
                    onExploreMetaStory(metaStory, event.currentTarget)}
                  data-focus-id={`meta-title-${metaStory.id}`}
                  aria-label={$_("landing.explore_meta_story")}
                >
                  <h2
                    class="slide-title"
                    style="--title-scale: {getTitleScale(metaStory.title)}"
                  >
                    {metaStory.title}
                  </h2>
                  <p class="slide-tagline">{metaStory.tagline}</p>
                  <span class="date-range-group">
                    <span class="separator">·</span>
                    <span class="date-range"
                      >{metaStory.date_range_start}–{metaStory.date_range_end}</span
                    >
                  </span>
                </button>
                <div class="slide-meta" on:click|stopPropagation>
                  <div class="button-container">
                    <button
                      class="person-count"
                      on:click={() => onFilterByMetaStory(metaStory)}
                      aria-label={$_("landing.filter_by_meta_story", {
                        title: metaStory.title,
                      })}
                    >
                      {$_("landing.filter")}
                    </button>
                    <button
                      class="explore-story"
                      on:click={(event) =>
                        onExploreMetaStory(metaStory, event.currentTarget)}
                      data-focus-id={`meta-explore-${metaStory.id}`}
                      aria-label={$_("landing.explore_meta_story")}
                    >
                      {$_("landing.timeline")}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        {/each}
      </div>

      {#if metaStories.length > 1}
        <button
          class="carousel-nav prev"
          on:click={handlePrevClick}
          aria-label={$_("landing.previous_slide")}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <polyline points="15 18 9 12 15 6"></polyline>
          </svg>
        </button>

        <button
          class="carousel-nav next"
          on:click={handleNextClick}
          aria-label={$_("landing.next_slide")}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <polyline points="9 18 15 12 9 6"></polyline>
          </svg>
        </button>

        <div class="carousel-indicators">
          {#each metaStories as _metaStoryItem, index}
            {@const slideLabel = $_("landing.go_to_slide", {
              number: index + 1,
            })}
            <button
              class="indicator"
              class:active={index === currentSlide}
              on:click={() => goToSlide(index)}
              aria-label={slideLabel}
              aria-current={index === currentSlide ? "true" : undefined}
            ></button>
          {/each}
        </div>
      {/if}

      {#if metaStories.length > 1}
        <!-- A real control, not a glyph that looks like one: it used to draw a
             pause icon that nothing happened on pressing, and screen readers
             were never told the state existed. -->
        <button
          type="button"
          class="playback-indicator"
          class:paused={isPaused}
          on:click={toggleAutoplay}
          aria-pressed={autoplayStopped}
          aria-label={autoplayStopped
            ? $_("landing.resume_carousel")
            : $_("landing.pause_carousel")}
        >
          {#if resumeTimerActive}
            {#key timerKey}
              <svg
                class="countdown-ring"
                width="32"
                height="32"
                viewBox="0 0 32 32"
                style="--duration: {RESUME_DELAY}ms;"
              >
                <circle
                  cx="16"
                  cy="16"
                  r="14"
                  fill="none"
                  stroke="rgba(148, 163, 184, 0.6)"
                  stroke-width="2"
                  stroke-dasharray="88 88"
                  transform="rotate(-90 16 16)"
                />
              </svg>
            {/key}
          {/if}
          <!-- Now that pressing it does something, the glyph names the action
               rather than the state: play to start the motion, pause to end
               it. -->
          <div class="playback-icon">
            {#if isPaused}
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="currentColor"
                aria-hidden="true"
              >
                <path d="M8 5v14l11-7z" />
              </svg>
            {:else}
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="currentColor"
                aria-hidden="true"
              >
                <rect x="6" y="4" width="4" height="16" rx="1" />
                <rect x="14" y="4" width="4" height="16" rx="1" />
              </svg>
            {/if}
          </div>
        </button>
      {/if}
    </div>
  </section>
{/if}

<style>
  .meta-story-carousel {
    width: 100%;
    margin: 0;
    overflow: hidden;
  }

  .carousel-container {
    position: relative;
    width: 100%;
    overflow: hidden;
    border-radius: 0;
    background: linear-gradient(
      135deg,
      rgba(15, 23, 42, 0.95) 0%,
      rgba(30, 41, 59, 0.95) 100%
    );
    border-top: 1px solid rgba(148, 163, 184, 0.2);
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
    border-left: none;
    border-right: none;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
  }

  @media (min-width: 768px) {
    .carousel-container {
      border-radius: 1rem;
      border: 1px solid rgba(148, 163, 184, 0.2);
    }
  }

  .carousel-track {
    display: flex;
    transition: transform 0.5s cubic-bezier(0.4, 0, 0.2, 1);
    cursor: grab;
    user-select: none;
  }

  .carousel-track:active {
    cursor: grabbing;
  }

  .carousel-slide {
    flex: 0 0 100%;
    min-width: 100%;
    padding: 0;
    box-sizing: border-box;
    position: relative;
    min-height: 300px;
    overflow: hidden;
  }

  .portrait-background {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 75%;
    display: flex;
    z-index: 0;
  }

  .portrait-column {
    flex: 1 1 0;
    max-width: 25%; /* Prevent extreme widening when few portraits */
    position: relative;
    border: none;
    background: none;
    padding: 0;
    cursor: pointer;
    /* Named rather than `all`: the only animated property is the hover
       widening, and `all` would have faded the focus ring below in over three
       tenths of a second — a focus indicator has to be there when focus is. */
    transition: flex 0.3s ease;
    margin-left: -5%;
  }

  /* The slanted mask sits on an inner element, not on the button itself: a
     clip-path clips the element's focus ring along with its corners, and these
     buttons come early in the tab order, so a keyboard reader lost their place
     on the entry page with nothing rendered to follow. */
  .portrait-clip {
    display: block;
    width: 100%;
    height: 100%;
    overflow: hidden;
    clip-path: polygon(0 0, 100% 8%, 100% 100%, 0 92%);
  }

  /* Drawn inside the button, because the columns deliberately overlap and an
     offset ring would slide under the neighboring portrait. */
  .portrait-column:focus-visible {
    outline: 3px solid #38bdf8;
    outline-offset: -3px;
    z-index: 2;
  }

  .portrait-column:first-child {
    margin-left: -2%;
  }

  .portrait-column:last-child {
    margin-right: -2%;
  }

  .portrait-column:hover {
    flex: 1.15;
    z-index: 1;
  }

  /* The resting 92% squeeze is done via layout, not transform: Chrome
     resamples transform-scaled images with low-quality compositor filtering,
     which aliases the downscaled portraits. Transforms only run on hover. */
  .portrait-clip img {
    width: 92%;
    margin-inline: 4%;
    height: 100%;
    object-fit: cover;
    object-position: center top;
    display: block;
    transition:
      transform 0.3s ease,
      width 0.3s ease,
      margin 0.3s ease;
  }

  .portrait-column:hover .portrait-clip img {
    width: 100%;
    margin-inline: 0;
    transform: scale(1.02);
  }

  /* Each portrait is a click target for that person's story, so hovering or
     focusing it names who it opens. The caption sits outside .portrait-clip,
     so the slanted mask cannot cut it.

     It sits at the very top of the column, because the bottom belongs to
     .slide-content: an opaque block that paints a layer above the portraits
     and grows with the headline it holds, so a caption anchored to the bottom
     was drawn underneath the title rather than on the face it names (#129).

     Two things share that top edge. The clip's slant starts the image lower at
     the right than at the left, so on a right-leaning column the caption sits
     above the cut rather than on the image; its own pill carries it. And
     .playback-indicator holds the same corner, 32px at 0.75rem in, so on a
     narrow slide its circle grazes the last column's caption. That control is
     translucent and the caption stays readable through it, which is the lesser
     cost: an offset large enough to clear it would drop every caption off the
     top edge to spare one column on one width. */
  .portrait-name {
    position: absolute;
    left: 50%;
    top: 0;
    transform: translateX(-50%);
    max-width: calc(100% - 1rem);
    padding: 0.2rem 0.55rem;
    border-radius: 999px;
    background: rgba(0, 0, 0, 0.65);
    color: #fff;
    font-size: 0.75rem;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  .portrait-column:hover .portrait-name,
  .portrait-column:focus-visible .portrait-name {
    opacity: 1;
  }

  .slide-content {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: 1;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    max-width: 100%;
    padding: 1.25rem 3.5rem 2.5rem 3.5rem;
    background: linear-gradient(
      to top,
      rgba(0, 0, 0, 1) 0%,
      rgba(0, 0, 0, 1) 60%,
      rgba(0, 0, 0, 0) 90%,
      rgba(0, 0, 0, 0) 0%
    );
  }

  @media (max-width: 640px) {
    .slide-content {
      padding: 1rem 3rem 2rem 3rem;
    }

    .button-container {
      flex-direction: column;
    }

    .button-container button {
      width: 100%;
    }
  }

  @media (min-width: 768px) {
    .slide-content {
      padding: 1.5rem 5rem 3rem 5rem;
    }
  }

  .slide-header {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .title-row {
    display: flex;
    flex-direction: row;
    align-items: baseline;
    gap: 0.4rem;
    flex-wrap: wrap;
    background: none;
    border: none;
    padding: 0;
    margin: 0;
    cursor: pointer;
    text-align: left;
    font-family: inherit;
    transition: opacity 0.2s ease;
  }

  .title-row:hover {
    opacity: 0.85;
  }

  .title-row:hover .slide-title {
    text-decoration: underline;
    text-decoration-color: rgba(226, 232, 240, 0.5);
    text-underline-offset: 4px;
  }

  .separator {
    color: #64748b;
    font-weight: 400;
    text-shadow:
      0 3px 10px rgba(0, 0, 0, 1),
      0 2px 6px rgba(0, 0, 0, 1),
      0 1px 3px rgba(0, 0, 0, 0.9);
  }

  .slide-title {
    font-size: calc(1.8rem * var(--title-scale, 1));
    line-height: 1.2;
    margin: 0;
    overflow-wrap: break-word;
    max-width: 100%;
    color: #e2e8f0;
    font-weight: 700;
    text-shadow:
      0 4px 12px rgba(0, 0, 0, 1),
      0 2px 8px rgba(0, 0, 0, 1),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .slide-tagline {
    font-size: 1rem;
    color: #cbd5e1;
    margin: 0;
    font-style: italic;
    text-shadow:
      0 3px 10px rgba(0, 0, 0, 1),
      0 2px 6px rgba(0, 0, 0, 1),
      0 1px 3px rgba(0, 0, 0, 0.9);
  }

  .slide-meta {
    margin-top: 0.25rem;
  }

  .person-count {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.25rem 0.75rem;
    border-radius: 0.375rem;
    background: rgba(56, 189, 248, 0.15);
    border: 1px solid rgba(56, 189, 248, 0.3);
    color: #38bdf8;
    font-weight: 500;
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.2s ease;
    font-family: inherit;
    text-shadow:
      0 3px 10px rgba(0, 0, 0, 1),
      0 2px 6px rgba(0, 0, 0, 1),
      0 1px 3px rgba(0, 0, 0, 0.9);
  }

  .person-count:hover {
    background: rgba(56, 189, 248, 0.25);
    border-color: rgba(56, 189, 248, 0.5);
    transform: translateY(-1px);
  }

  .person-count:active {
    transform: translateY(0);
  }

  .button-container {
    display: flex;
    gap: 0.75rem;
    flex-direction: row;
  }

  .explore-story {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.25rem 0.75rem;
    border-radius: 0.375rem;
    background: rgba(56, 189, 248, 0.15);
    border: 1px solid rgba(56, 189, 248, 0.3);
    color: #38bdf8;
    font-weight: 500;
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.2s ease;
    font-family: inherit;
    text-shadow:
      0 3px 10px rgba(0, 0, 0, 1),
      0 2px 6px rgba(0, 0, 0, 1),
      0 1px 3px rgba(0, 0, 0, 0.9);
  }

  .explore-story:hover {
    background: rgba(56, 189, 248, 0.25);
    border-color: rgba(56, 189, 248, 0.5);
    transform: translateY(-1px);
  }

  .explore-story:active {
    transform: translateY(0);
  }

  .date-range {
    color: #cbd5e1;
    text-shadow:
      0 3px 10px rgba(0, 0, 0, 1),
      0 2px 6px rgba(0, 0, 0, 1),
      0 1px 3px rgba(0, 0, 0, 0.9);
  }

  .date-range-group {
    white-space: nowrap;
  }

  .carousel-nav {
    position: absolute;
    bottom: 25%;
    transform: translateY(50%);
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: rgba(15, 23, 42, 0.3);
    border: 1px solid rgba(148, 163, 184, 0.2);
    color: rgba(226, 232, 240, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.2s ease;
    z-index: 10;
    backdrop-filter: blur(4px);
  }

  .carousel-nav:hover {
    background: rgba(15, 23, 42, 0.6);
    border-color: rgba(56, 189, 248, 0.4);
    color: #38bdf8;
  }

  .carousel-nav.prev {
    left: 0.125rem;
  }

  .carousel-nav.next {
    right: 0.125rem;
  }

  @media (min-width: 640px) {
    .carousel-nav.prev {
      left: 0.25rem;
    }

    .carousel-nav.next {
      right: 0.25rem;
    }
  }

  .carousel-indicators {
    position: absolute;
    bottom: 0.75rem;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    gap: 0.5rem;
    z-index: 10;
  }

  .indicator {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: rgba(148, 163, 184, 0.4);
    border: none;
    cursor: pointer;
    transition: all 0.2s ease;
    padding: 0;
  }

  .indicator:hover {
    background: rgba(148, 163, 184, 0.6);
  }

  .indicator.active {
    background: #38bdf8;
    width: 24px;
    border-radius: 4px;
  }

  @media (min-width: 768px) {
    .carousel-slide {
      min-height: 400px;
    }

    .slide-title {
      font-size: calc(2.4rem * var(--title-scale, 1));
    }

    .slide-tagline {
      font-size: 1.1rem;
    }

    .carousel-nav {
      width: 48px;
      height: 48px;
    }

    .carousel-nav.prev {
      left: 0.5rem;
    }

    .carousel-nav.next {
      right: 0.5rem;
    }

    .carousel-indicators {
      bottom: 1rem;
    }
  }

  .playback-indicator {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.4);
    color: rgba(226, 232, 240, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
    backdrop-filter: blur(4px);
    border: none;
    padding: 0;
    cursor: pointer;
    transition:
      background 0.2s ease,
      color 0.2s ease;
  }

  .playback-indicator.paused,
  .playback-indicator:hover,
  .playback-indicator:focus-visible {
    background: rgba(0, 0, 0, 0.6);
    color: rgba(226, 232, 240, 0.9);
  }

  .playback-indicator:focus-visible {
    outline: 3px solid #38bdf8;
    outline-offset: 2px;
  }

  .playback-icon {
    position: absolute;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .countdown-ring {
    position: absolute;
    top: 0;
    left: 0;
  }

  .countdown-ring circle {
    animation: countdown-ring var(--duration, 10s) linear forwards;
  }

  @keyframes countdown-ring {
    0% {
      stroke-dashoffset: 0;
    }
    100% {
      stroke-dashoffset: 88;
    }
  }
</style>
