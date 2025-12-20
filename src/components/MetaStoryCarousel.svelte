<script>
  import { _ } from "../stores/language";
  import { displayName } from "../utils/helpers.js";

  export let metaStories = [];
  export let persons = [];
  export let getStyle = () => ({});
  export let onSelectPerson = () => {};
  export let onFilterByMetaStory = () => {};

  let currentSlide = 0;
  let autoplayInterval;
  let carouselElement;
  let isDragging = false;
  let startX = 0;
  let scrollLeft = 0;

  // Auto-advance every 5 seconds
  function startAutoplay() {
    stopAutoplay();
    autoplayInterval = setInterval(() => {
      if (!isDragging) {
        nextSlide();
      }
    }, 5000);
  }

  function stopAutoplay() {
    if (autoplayInterval) {
      clearInterval(autoplayInterval);
      autoplayInterval = null;
    }
  }

  function nextSlide() {
    currentSlide = (currentSlide + 1) % metaStories.length;
  }

  function prevSlide() {
    currentSlide = (currentSlide - 1 + metaStories.length) % metaStories.length;
  }

  function goToSlide(index) {
    currentSlide = index;
    stopAutoplay();
    startAutoplay();
  }

  function handleMouseDown(e) {
    isDragging = true;
    startX = e.pageX - carouselElement.offsetLeft;
    scrollLeft = carouselElement.scrollLeft;
    carouselElement.style.cursor = "grabbing";
    stopAutoplay();
  }

  function handleMouseUp() {
    isDragging = false;
    carouselElement.style.cursor = "grab";
    startAutoplay();
  }

  function handleMouseMove(e) {
    if (!isDragging) return;
    e.preventDefault();
    const x = e.pageX - carouselElement.offsetLeft;
    const walk = (x - startX) * 2;
    carouselElement.scrollLeft = scrollLeft - walk;
  }

  function handleTouchStart(e) {
    isDragging = true;
    startX = e.touches[0].pageX - carouselElement.offsetLeft;
    scrollLeft = carouselElement.scrollLeft;
    stopAutoplay();
  }

  function handleTouchEnd() {
    isDragging = false;
    startAutoplay();
  }

  function handleTouchMove(e) {
    if (!isDragging) return;
    const x = e.touches[0].pageX - carouselElement.offsetLeft;
    const walk = (x - startX) * 2;
    carouselElement.scrollLeft = scrollLeft - walk;
  }

  function getPersonsForMetaStory(metaStory) {
    if (!metaStory?.person_ids) return [];

    // Remove duplicates from person_ids first
    const uniquePersonIds = [...new Set(metaStory.person_ids)];

    return uniquePersonIds
      .map((id) => persons.find((p) => p.id === id))
      .filter(Boolean)
      .sort((a, b) => {
        // Parse birth years from birthDate (format: YYYY-MM-DD or YYYY)
        const yearA = a.birthDate ? parseInt(a.birthDate.split("-")[0]) : Infinity;
        const yearB = b.birthDate ? parseInt(b.birthDate.split("-")[0]) : Infinity;
        return yearA - yearB;
      })
      .slice(0, 6); // Limit to 6 persons for display
  }

  function getThumbnailUrl(imageUrl, width = 80) {
    if (!imageUrl || typeof imageUrl !== "string") return imageUrl;

    // Optimize Wikimedia Commons images
    if (imageUrl.includes("upload.wikimedia.org/wikipedia/commons/")) {
      if (imageUrl.includes("/thumb/")) {
        return imageUrl.replace(/\/\d+px-([^/]+)$/, `/${width}px-$1`);
      }

      const parts = imageUrl.split("/wikipedia/commons/");
      if (parts.length === 2) {
        const [base, path] = parts;
        const filename = path.split("/").pop();
        const thumbFilename = filename.toLowerCase().endsWith(".svg")
          ? `${filename}.png`
          : filename;
        return `${base}/wikipedia/commons/thumb/${path}/${width}px-${thumbFilename}`;
      }
    }

    return imageUrl;
  }

  // Start autoplay on mount
  import { onMount, onDestroy } from "svelte";

  onMount(() => {
    startAutoplay();
  });

  onDestroy(() => {
    stopAutoplay();
  });

  $: if (metaStories.length === 0) {
    stopAutoplay();
  }
</script>

{#if metaStories.length > 0}
  <section class="meta-story-carousel">
    <div class="carousel-container">
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
                    {#if person?.portrait?.image}
                      <img
                        src={getThumbnailUrl(person.portrait.image, 200)}
                        srcset={`${getThumbnailUrl(person.portrait.image, 200)} 1x, ${getThumbnailUrl(person.portrait.image, 400)} 2x`}
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
                <h2 class="slide-title">{metaStory.title}</h2>
                <p class="slide-tagline">{metaStory.tagline}</p>
                <div class="slide-meta">
                  <button
                    class="person-count"
                    on:click={() => onFilterByMetaStory(metaStory)}
                    aria-label={$_("landing.filter_by_meta_story", {
                      title: metaStory.title,
                    })}
                  >
                    {$_("landing.select_persons", {
                      count: metaStory.person_count,
                    })}
                  </button>
                  <span class="date-range"
                    >{metaStory.date_range_start}–{metaStory.date_range_end}</span
                  >
                </div>
              </div>
            </div>
          </div>
        {/each}
      </div>

      {#if metaStories.length > 1}
        <button
          class="carousel-nav prev"
          on:click={prevSlide}
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
          on:click={nextSlide}
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
          {#each metaStories as metaStoryItem, index}
            {@const slideLabel = $_("landing.go_to_slide", { number: index + 1 })}
            <button
              class="indicator"
              class:active={index === currentSlide}
              on:click={() => goToSlide(index)}
              aria-label={slideLabel}
            />
          {/each}
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
    border-radius: 1rem;
    background: linear-gradient(
      135deg,
      rgba(15, 23, 42, 0.95) 0%,
      rgba(30, 41, 59, 0.95) 100%
    );
    border: 1px solid rgba(148, 163, 184, 0.2);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
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
    flex: 1;
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
      rgba(0, 0, 0, 1) 25%,
      rgba(0, 0, 0, 0.9) 40%,
      rgba(0, 0, 0, 0) 70%
    );
  }

  @media (max-width: 640px) {
    .slide-content {
      padding: 1rem 3rem 2rem 3rem;
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
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    font-size: 0.85rem;
    color: #94a3b8;
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
</style>
