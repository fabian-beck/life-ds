# Exploratory Charters

Select charters by risk; do not attempt every item in every session.

## Personas

- **First-time mobile visitor:** discovers the interface without prior product
  knowledge and expects touch-friendly controls.
- **Curious researcher:** follows chronology, maps, sources, people, networks,
  and collections while retaining context.
- **Keyboard or low-vision visitor:** uses keyboard navigation, visible focus,
  browser zoom, and high contrast where available.
- **Impatient visitor:** changes language, navigates quickly, reloads deep
  links, and uses Back at unexpected points.

## Charters

### Discovery

Explore language choice, search, role filters, clearing state, story cards,
collection discovery, and the landing map. Look for understandable feedback
and useful empty or loading states.

### Person story

Open from both a card and a direct URL. Explore overview, chapters, event
slides, arrow/wheel/swipe navigation, timeline, map state, close, reload, and
Back behavior.

### Rich interaction

Explore annotations, person chips, the network modal, image viewer, image
navigation and zoom, captions, and source links. Check modal dismissal and
whether context is preserved.

### Collection story

Open a collection from the landing page. Explore its timeline, sticky controls,
map and network sections, enter a person story, then return to the same context.

### Responsive stress

Use narrow mobile, short landscape, and desktop at 200% zoom. Look for
horizontal overflow, clipped text, obscured controls, unstable layout, and long
German or French copy.

### Resilience

Reload a deep link, switch languages rapidly, navigate during loading, and
observe failed images, failed requests, errors, and recovery behavior. Do not
deliberately damage persisted or source data.

### Accessibility heuristic

Check keyboard reachability, logical focus, visible focus, modal focus and
closing, meaningful accessible names, readable contrast, zoom, and practical
touch target sizes. Label this a heuristic review, not a conformance audit.

## Mode selection

- **Smoke:** first-time persona; Discovery plus one Person story and one
  Collection story on the primary viewport.
- **Focused:** persona matching the diff; changed-feature charter plus one
  adjacent journey and one stress dimension.
- **Release:** rotate at least three personas; cover all feature families in
  mobile, desktop, short landscape, English, German, and French. Sample rather
  than exhaustively permuting combinations.
