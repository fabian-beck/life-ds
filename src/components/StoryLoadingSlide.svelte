<script>
  /*
   * What stands in for the overview slide while a life is being fetched.
   *
   * The skeleton traces the real slide's column — portrait block, then name,
   * years, roles and summary — so the layout the reader is looking at does not
   * jump when the data arrives. That shared geometry is the `.overview-content`
   * and `.overview-text` rule in `app.css`, which `OverviewSlide` uses too; what
   * is left here is the shimmer itself and the spinner underneath it.
   *
   * The enclosing `<section class="slide overview loading-slide">` stays in
   * `StoryView`, whose scoped slide rules cannot reach into a component.
   */
  import { _ } from "../stores/language";

  const { loadingStage = null } = $props();

  // Only the network stage names itself. The initial and dataset stages are
  // both fetching the life, which is what the reader is waiting for.
  const messageKey = $derived(
    loadingStage === "network" ? "story.loading_network" : "story.loading_life"
  );
</script>

<div class="content overview-content">
  <div class="skeleton-portrait"></div>
  <div class="overview-text">
    <div class="skeleton-text skeleton-eyebrow"></div>
    <div class="skeleton-text skeleton-title"></div>
    <div class="skeleton-text skeleton-years"></div>
    <div class="skeleton-text skeleton-roles"></div>
    <div class="skeleton-paragraph">
      <div class="skeleton-text skeleton-line"></div>
      <div class="skeleton-text skeleton-line"></div>
      <div class="skeleton-text skeleton-line" style="width: 80%;"></div>
    </div>
  </div>
</div>

<div class="loading-indicator">
  <div class="spinner"></div>
  <p class="loading-text">{$_(messageKey)}</p>
</div>

<style>
  .skeleton-portrait {
    width: min(220px, 80vw);
    height: min(220px, 30vh);
    border-radius: 1rem;
    background: linear-gradient(
      90deg,
      rgba(148, 163, 184, 0.1) 0%,
      rgba(148, 163, 184, 0.2) 50%,
      rgba(148, 163, 184, 0.1) 100%
    );
    background-size: 200% 100%;
    animation: shimmer 2s infinite;
  }

  .skeleton-text {
    height: 1em;
    border-radius: 0.25rem;
    background: linear-gradient(
      90deg,
      rgba(148, 163, 184, 0.1) 0%,
      rgba(148, 163, 184, 0.2) 50%,
      rgba(148, 163, 184, 0.1) 100%
    );
    background-size: 200% 100%;
    animation: shimmer 2s infinite;
    margin-bottom: 0.5rem;
  }

  .skeleton-eyebrow {
    width: 120px;
    height: 0.7rem;
  }

  .skeleton-title {
    width: 280px;
    max-width: 90%;
    height: 1.5rem;
    margin-top: 0.5rem;
  }

  .skeleton-years {
    width: 100px;
    height: 0.9rem;
  }

  .skeleton-roles {
    width: 200px;
    max-width: 70%;
    height: 0.85rem;
  }

  .skeleton-paragraph {
    margin-top: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .skeleton-line {
    width: 100%;
    height: 0.9rem;
  }

  @keyframes shimmer {
    0% {
      background-position: 200% 0;
    }
    100% {
      background-position: -200% 0;
    }
  }

  .loading-indicator {
    position: absolute;
    bottom: 4rem;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    z-index: 10;
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid rgba(148, 163, 184, 0.2);
    border-top-color: var(--story-secondary, #38bdf8);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .loading-text {
    margin: 0;
    font-size: 0.9rem;
    color: rgba(148, 163, 184, 0.9);
    font-weight: 500;
    animation: pulse 2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.5;
    }
  }
</style>
