<script>
  import CloseButton from "./CloseButton.svelte";
  import { _ } from "../stores/language";

  export let show = false;
  export let onClose = () => {};

  function handleBackdropClick(event) {
    if (event.target === event.currentTarget) {
      onClose();
    }
  }
</script>

{#if show}
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <div
    class="modal-backdrop"
    on:click={handleBackdropClick}
    on:keydown={(e) => e.key === 'Escape' && onClose()}
    role="dialog"
    aria-modal="true"
  >
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
    <div class="modal-content" on:click|stopPropagation role="document">
      <CloseButton
        variant="light"
        size="small"
        position="absolute"
        ariaLabel={$_("landing.ai_modal_close")}
        on:click={onClose}
      />
      <h2>{$_("landing.ai_modal_title")}</h2>
      <div class="modal-body">
        <p>
          <strong>{$_("landing.ai_how_it_works")}</strong>
          {$_("landing.ai_description")}
        </p>
        <ul>
          <li>{$_("landing.ai_step_1")}</li>
          <li>{$_("landing.ai_step_2")}</li>
          <li>{$_("landing.ai_step_3")}</li>
          <li>{$_("landing.ai_step_4")}</li>
          <li>{$_("landing.ai_step_5")}</li>
        </ul>
        <p>
          <strong>{$_("landing.ai_accuracy")}</strong>
          {$_("landing.ai_accuracy_text")}
        </p>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
    overflow-y: auto;
  }

  .modal-content {
    position: relative;
    max-width: 600px;
    width: 100%;
    max-height: calc(100vh - 2rem);
    background: rgba(15, 23, 42, 0.95);
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 1rem;
    padding: 1.5rem;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
    margin: auto;
    display: flex;
    flex-direction: column;
  }

  .modal-content h2 {
    margin: 0 0 0.875rem 0;
    font-size: 1.35rem;
    color: #fbbf24;
  }

  .modal-body {
    font-size: 0.9rem;
    line-height: 1.5;
    color: #cbd5e1;
    overflow-y: auto;
    flex: 1 1 auto;
    min-height: 0;
  }

  .modal-body strong {
    color: #fbbf24;
  }

  .modal-body p {
    margin: 0 0 0.625rem 0;
  }

  .modal-body p:last-child {
    margin-bottom: 0;
  }

  .modal-body ul {
    margin: 0.5rem 0;
    padding-left: 1.25rem;
  }

  .modal-body li {
    margin-bottom: 0.375rem;
  }

  .modal-body li:last-child {
    margin-bottom: 0;
  }
</style>
