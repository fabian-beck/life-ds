<script>
  import CloseButton from "./CloseButton.svelte";
  import { _ } from "../stores/language";
  import { dialog } from "../utils/dialog.js";

  // The one address in the notice that is not translated prose, kept here so
  // it is stated once rather than in both locale files.
  const contactEmail = "fabian.beck@uni-bamberg.de";

  const { show = false, onClose = () => {} } = $props();

  function handleBackdropClick(event) {
    if (event.target === event.currentTarget) {
      onClose();
    }
  }
</script>

{#if show}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div data-dialog-overlay class="modal-backdrop" onclick={handleBackdropClick}>
    <div
      class="modal-content"
      use:dialog={{ onClose, initialFocus: ".close-button" }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="privacy-title"
      tabindex="-1"
    >
      <CloseButton
        variant="light"
        size="small"
        position="absolute"
        ariaLabel={$_("landing.privacy_modal_close")}
        on:click={onClose}
      />
      <h2 id="privacy-title">{$_("landing.privacy_modal_title")}</h2>
      <div class="modal-body">
        <p>
          <strong>{$_("landing.privacy_no_tracking")}</strong>
          {$_("landing.privacy_no_tracking_text")}
        </p>
        <p>
          <strong>{$_("landing.privacy_hosting")}</strong>
          {$_("landing.privacy_hosting_text")}
        </p>
        <p>
          <strong>{$_("landing.privacy_third_party")}</strong>
          {$_("landing.privacy_third_party_text")}
        </p>
        <p>
          <strong>{$_("landing.privacy_storage")}</strong>
          {$_("landing.privacy_storage_text")}
        </p>
        <p>
          <strong>{$_("landing.privacy_contact")}</strong>
          {$_("landing.privacy_contact_text")}
          <a class="contact-link" href="mailto:{contactEmail}">{contactEmail}</a
          >.
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

  .contact-link {
    color: #fbbf24;
    text-decoration: underline;
    text-underline-offset: 0.2em;
  }

  .contact-link:hover {
    color: #fcd34d;
  }
</style>
