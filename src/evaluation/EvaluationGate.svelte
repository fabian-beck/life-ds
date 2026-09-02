<script>
  import { _ } from "../stores/language";
  import { dialog } from "../utils/dialog.js";
  import { normalizeParticipantId } from "./participant.js";

  // The first thing a reader sees on the evaluation deployment: who they are.
  // It cannot be dismissed, because nothing behind it may be logged without an
  // id, and the whole deployment exists to log.
  const { onSubmit = () => {} } = $props();

  let value = $state("");
  let invalid = $state(false);

  function submit(event) {
    event.preventDefault();
    const id = normalizeParticipantId(value);
    if (!id) {
      invalid = true;
      return;
    }
    invalid = false;
    onSubmit(id);
  }
</script>

<div data-dialog-overlay class="gate-backdrop">
  <div
    class="gate"
    use:dialog={{ onClose: () => {}, initialFocus: "input" }}
    role="dialog"
    aria-modal="true"
    aria-labelledby="evaluation-gate-title"
    tabindex="-1"
  >
    <form onsubmit={submit}>
      <p class="gate-kicker">{$_("evaluation.gate_kicker")}</p>
      <h2 id="evaluation-gate-title">{$_("evaluation.gate_title")}</h2>
      <p class="gate-text">{$_("evaluation.gate_text")}</p>
      <p class="gate-text">{$_("evaluation.gate_consent")}</p>
      <label class="gate-label" for="evaluation-participant">
        {$_("evaluation.gate_label")}
      </label>
      <input
        id="evaluation-participant"
        class="gate-input"
        class:invalid
        type="text"
        autocomplete="off"
        autocapitalize="off"
        spellcheck="false"
        maxlength="32"
        placeholder={$_("evaluation.gate_placeholder")}
        aria-describedby="evaluation-gate-hint"
        aria-invalid={invalid}
        bind:value
      />
      <p id="evaluation-gate-hint" class="gate-hint" class:invalid>
        {invalid ? $_("evaluation.gate_invalid") : $_("evaluation.gate_hint")}
      </p>
      <button type="submit" class="gate-submit">
        {$_("evaluation.gate_submit")}
      </button>
    </form>
  </div>
</div>

<style>
  .gate-backdrop {
    position: fixed;
    inset: 0;
    z-index: 1100;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
    background: rgba(2, 6, 23, 0.92);
    overflow-y: auto;
  }

  .gate {
    width: 100%;
    max-width: 480px;
    margin: auto;
    padding: 1.5rem;
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 1rem;
    background: rgba(15, 23, 42, 0.98);
    color: #cbd5e1;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  }

  .gate-kicker {
    margin: 0 0 0.5rem;
    color: #94a3b8;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  h2 {
    margin: 0 0 0.875rem;
    color: #fbbf24;
    font-size: 1.35rem;
  }

  .gate-text {
    margin: 0 0 0.75rem;
    font-size: 0.9rem;
    line-height: 1.5;
  }

  .gate-label {
    display: block;
    margin: 1rem 0 0.375rem;
    color: #e2e8f0;
    font-size: 0.85rem;
    font-weight: 600;
  }

  .gate-input {
    width: 100%;
    padding: 0.7rem 0.85rem;
    border: 1px solid rgba(148, 163, 184, 0.5);
    border-radius: 0.6rem;
    background: rgba(2, 6, 23, 0.6);
    color: #f8fafc;
    font-size: 1.05rem;
    font-family: inherit;
  }

  .gate-input:focus-visible {
    outline: 2px solid #fbbf24;
    outline-offset: 2px;
  }

  .gate-input.invalid {
    border-color: #f87171;
  }

  .gate-hint {
    margin: 0.375rem 0 1rem;
    color: #94a3b8;
    font-size: 0.8rem;
  }

  .gate-hint.invalid {
    color: #fca5a5;
  }

  .gate-submit {
    width: 100%;
    padding: 0.75rem 1rem;
    border: 0;
    border-radius: 0.6rem;
    background: #fbbf24;
    color: #0f172a;
    font-size: 1rem;
    font-weight: 700;
    font-family: inherit;
    cursor: pointer;
  }

  .gate-submit:hover {
    background: #fcd34d;
  }

  .gate-submit:focus-visible {
    outline: 2px solid #f8fafc;
    outline-offset: 2px;
  }
</style>
