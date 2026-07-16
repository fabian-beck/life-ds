<script>
  import { _ } from "../stores/language";
  import { displayName } from "../utils/helpers.js";
  import { getThumbnailUrl } from "../utils/storyHelpers.js";

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

  // Auto-advance every 5 seconds
  function startAutoplay() {
    if (isHovered || isDragging) {
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
    resumeTimerActive = true;
    timerKey += 1;
    resumeTimeout = setTimeout(() => {
      resumeTimerActive = false;
      startAutoplay();
    }, RESUME_DELAY);
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
  }

  function handleNextClick() {
    nextSlide();
    pauseWithResumeTimer();
  }

  function goToSlide(index) {
    currentSlide = index;
    pauseWithResumeTimer();
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
    if (e.pointerType === 'touch') return;
    // Ignore internal transitions within the carousel
    if (sectionElement && e?.relatedTarget && sectionElement.contains(e.relatedTarget)) return;
    isHovered = true;

    // Pause autoplay with resume timer as fallback to prevent stuck states
    pauseWithResumeTimer();
  }

  function handleMouseLeave(e) {
    // Ignore internal transitions within the carousel
    if (sectionElement && e?.relatedTarget && sectionElement.contains(e.relatedTarget)) return;
    if (!isHovered) return;
    isHovered = false;

    // Only resume if we are not dragging
    if (!isDragging) {
      isPaused = false;
      startAutoplay();
    }
  }

  function getPersonsForMetaStory(metaStory) {
    if (!metaStory?.person_ids) return [];

    // Remove duplicates from person_ids first
    const uniquePersonIds = [...new Set(metaStory.person_ids)];

    const personsForStory = uniquePersonIds
      .map((id) => persons.find((p) => p.id === id))
      .filter(Boolean)
      .sort((a, b) => {
        // Parse birth years from birthDate (format: YYYY-MM-DD or YYYY)
        const yearA = a.birthDate ? parseInt(a.birthDate.split("-")[0]) : Infinity;
        const yearB = b.birthDate ? parseInt(b.birthDate.split("-")[0]) : Infinity;
        return yearA - yearB;
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
    startAutoplay();
  });

  onDestroy(() => {
    stopAutoplay();
    cancelResumeTimer();
  });

  $: if (metaStories.length === 0) {
    stopAutoplay();
  } else if (metaStories.length > 0 && !autoplayInterval && !isPaused && !isDragging && !isHovered) {
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
          <div class="carousel-slide" class:active={index === currentSlide}>
            {#if storyPersons.length > 0}
              <div class="portrait-background">
                {#each storyPersons as person (person.id)}
                  <button
                    class="portrait-column"
                    on:click={() => onSelectPerson(person.id)}
                    aria-label={`View ${displayName(person.name)}'s story`}
                  >
                    {#if person?.portrait}
                      <img
                        src={getThumbnailUrl(person.portrait, 600)}
                        srcset={`${getThumbnailUrl(person.portrait, 600)} 1x, ${getThumbnailUrl(person.portrait, 1200)} 2x`}
                        alt={person.portrait.alt ??
                          `Portrait of ${displayName(person.name)}`}
                        loading="lazy"
                        decoding="async"
                      />
                    {/if}
                  </button>
                {/each}
              </div>
            {/if}

            <div class="slide-content">
              <div class="slide-header">
                <button
                  class="title-row"
                  on:click={() => onExploreMetaStory(metaStory)}
                  aria-label={$_("landing.explore_meta_story")}
                >
                  <h2 class="slide-title">{metaStory.title}</h2>
                  <p class="slide-tagline">{metaStory.tagline}</p>
                  <span class="separator">·</span>
                  <span class="date-range"
                    >{metaStory.date_range_start}–{metaStory.date_range_end}</span
                  >
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
                      on:click={() => onExploreMetaStory(metaStory)}
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
            {@const slideLabel = $_("landing.go_to_slide", { number: index + 1 })}
            <button
              class="indicator"
              class:active={index === currentSlide}
              on:click={() => goToSlide(index)}
              aria-label={slideLabel}
            ></button>
          {/each}
        </div>
      {/if}

      {#if metaStories.length > 1}
        <div class="playback-indicator" class:paused={isPaused} aria-hidden="true">
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
          <div class="playback-icon">
            {#if isPaused}
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="currentColor"
              >
                <rect x="6" y="4" width="4" height="16" rx="1" />
                <rect x="14" y="4" width="4" height="16" rx="1" />
              </svg>
            {:else}
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="currentColor"
              >
                <path d="M8 5v14l11-7z" />
              </svg>
            {/if}
          </div>
        </div>
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
    overflow: hidden;
    border: none;
    background: none;
    padding: 0;
    cursor: pointer;
    transition: all 0.3s ease;
    clip-path: polygon(0 0, 100% 8%, 100% 100%, 0 92%);
    margin-left: -5%;
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

  .portrait-column img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center top;
    display: block;
    transition: transform 0.3s ease;
    transform: scaleX(0.92);
  }

  .portrait-column:hover img {
    transform: scaleX(1) scale(1.02);
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
    font-size: 1.8rem;
    line-height: 1.2;
    margin: 0;
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
      font-size: 2.4rem;
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
    pointer-events: none;
    transition: background 0.2s ease, color 0.2s ease;
  }

  .playback-indicator.paused {
    background: rgba(0, 0, 0, 0.6);
    color: rgba(226, 232, 240, 0.9);
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
