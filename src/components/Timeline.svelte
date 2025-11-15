<script>
  import { mdiChevronLeft, mdiChevronRight, mdiHome } from "@mdi/js";

  export let activeIndex = 0;
  export let totalSlides = 0;
  export let activeEventIndex = -1;
  export let hasMultipleEvents = false;
  export let indicatorProgress = 0;
  export let indicatorIcons = [];
  export let onPrevSlide = () => {};
  export let onNextSlide = () => {};
  export let onGoToEvent = () => {};
  export let onScrollToIndex = () => {};

  $: totalPanels = totalSlides > 0 ? totalSlides + 1 : 1; // +1 for overview slide
  $: hasEvents = totalSlides > 0;
</script>

{#if hasEvents}
  <div
    class="indicator"
    role="group"
    aria-label={`Event ${activeEventIndex + 1} of ${totalSlides}`}
    style={`--indicator-progress: ${indicatorProgress}`}
  >
    <div class="indicator-content">
      {#if totalPanels > 1}
        <div class="indicator-nav">
          <button
            type="button"
            class="nav-btn prev"
            on:click={onPrevSlide}
            aria-label="Go to previous slide"
            disabled={activeIndex === 0}
          >
            <svg
              class="icon"
              viewBox="0 0 24 24"
              role="presentation"
              aria-hidden="true"
            >
              <path d={mdiChevronLeft} />
            </svg>
          </button>
          <button
            type="button"
            class="nav-btn next"
            on:click={onNextSlide}
            aria-label="Go to next slide"
            disabled={activeIndex >= totalPanels - 1}
          >
            <svg
              class="icon"
              viewBox="0 0 24 24"
              role="presentation"
              aria-hidden="true"
            >
              <path d={mdiChevronRight} />
            </svg>
          </button>
        </div>
      {/if}
      <div class="indicator-track" class:single={!hasMultipleEvents}>
        <div class="dots-container">
          {#if activeIndex > 0}
            <span
              class="indicator-highlight"
              class:single={!hasMultipleEvents}
            />
          {/if}
          <button
            type="button"
            class="dot square"
            class:active={activeIndex === 0}
            on:click={() => onScrollToIndex(0)}
            aria-label="Show overview"
            aria-current={activeIndex === 0 ? "true" : undefined}
          >
            <svg
              class="dot-icon"
              viewBox="0 0 24 24"
              role="img"
              aria-hidden="true"
            >
              <path d={mdiHome} />
            </svg>
          </button>
          {#each Array(totalSlides) as _, idx}
            <button
              type="button"
              class="dot"
              class:active={idx === activeEventIndex}
              on:click={() => onGoToEvent(idx)}
              aria-label={`Show event ${idx + 1} of ${totalSlides}`}
              aria-current={idx === activeEventIndex ? "true" : undefined}
            >
              <svg
                class="dot-icon"
                viewBox="0 0 24 24"
                role="img"
                aria-hidden="true"
              >
                <path d={indicatorIcons[idx]} />
              </svg>
            </button>
          {/each}
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .indicator {
    --dot-size: clamp(1.25rem, 3vw, 1.6rem);
    --dot-gap: 0rem;
    position: fixed;
    bottom: 1.25rem;
    left: 50%;
    transform: translateX(-50%);
    width: min(96vw, 1020px);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    pointer-events: none;
    z-index: 5;
  }

  /* Keep the indicator visually present but allow underlying slides to receive
     pointer events (so dragging/panning works anywhere). Only the nav buttons
     inside the indicator should accept pointer events. */
  .indicator-content {
    pointer-events: auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    width: 100%;
  }

  .indicator-nav {
    pointer-events: auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    gap: 1.25rem;
  }

  .indicator-track {
    pointer-events: auto;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    padding: 0.65rem 0.75rem;
    border-radius: 9999px;
    background: rgba(15, 23, 42, 0.65);
    backdrop-filter: blur(6px);
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.25);
    border: 1px solid rgba(148, 163, 184, 0.2);
  }

  .indicator-track.single {
    justify-content: center;
    width: auto;
    min-width: auto;
  }

  .dots-container {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    max-width: min(90vw, 860px);
  }

  .nav-btn {
    pointer-events: auto;
    width: 2.6rem;
    height: 2.6rem;
    border-radius: 999px;
    border: 1px solid var(--story-primary, rgba(148, 163, 184, 0.35));
    background: rgba(255, 255, 255, 0.05);
    color: var(--story-primary, #e2e8f0);
    font-size: 1.15rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    flex: 0 0 auto;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      color 0.2s ease,
      transform 0.2s ease;
  }

  .nav-btn:hover,
  .nav-btn:focus {
    background: rgba(255, 255, 255, 0.15);
    border-color: var(--story-primary, rgba(148, 163, 184, 0.6));
    transform: scale(1.05);
    outline: none;
  }

  .nav-btn:disabled {
    opacity: 0.35;
    cursor: default;
    transform: none;
  }

  .indicator-highlight {
    position: absolute;
    top: 50%;
    left: 0;
    width: var(--dot-size);
    height: var(--dot-size);
    border-radius: 9999px;
    background: var(--story-secondary, rgba(56, 189, 248, 0.45));
    opacity: 0.45;
    transform: translateX(
        calc(var(--indicator-progress) * (100% - var(--dot-size)))
      )
      translateY(-50%);
    transition:
      transform 0.35s cubic-bezier(0.22, 1, 0.36, 1),
      background-color 0.3s ease;
    z-index: 0;
    pointer-events: none;
  }

  .indicator-highlight.single {
    left: 50%;
    transform: translate(-50%, -50%);
  }

  .dot {
    appearance: none;
    border: none;
    padding: 0;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    position: relative;
    z-index: 1;
    width: var(--dot-size);
    height: var(--dot-size);
    border-radius: 9999px;
    background: rgba(148, 163, 184, 0.3);
    transition:
      background-color 0.25s ease,
      transform 0.25s ease;
    flex: 0 0 auto;
  }

  .dot.square {
    border-radius: 20%;
  }

  .dot.active {
    background: var(--story-secondary, #38bdf8);
    transform: scale(1.2);
  }

  .dot-icon {
    width: calc(var(--dot-size) * 0.72);
    height: calc(var(--dot-size) * 0.72);
    fill: rgba(226, 232, 240, 0.95);
    transition:
      fill 0.25s ease,
      transform 0.25s ease;
  }

  .dot.active .dot-icon {
    fill: #0f172a;
    transform: scale(1.05);
  }

  .dot:focus-visible {
    outline: 2px solid var(--story-secondary, #38bdf8);
    outline-offset: 2px;
  }

  .icon {
    width: 1.1em;
    height: 1.1em;
    fill: currentColor;
    flex: 0 0 auto;
  }

  .nav-btn .icon {
    width: 1.2em;
    height: 1.2em;
  }
</style>
