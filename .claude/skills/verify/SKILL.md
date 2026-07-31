---
name: verify
description: Build, run, and drive the Life Data Stories app to verify a change end-to-end.
---

# Verifying changes in this repo

## Build & serve

```bash
npm install            # if node_modules is missing (vite: not found)
npm run build          # vite build → dist/
npm run preview -- --port 4173 --strictPort   # serve dist/ in the background
```

`npm run dev` (port 5173) also works for iterating without rebuilding.

## Drive with Playwright

The repository's own Playwright works in web sessions—`npm run test:interface`
and `npx playwright test` both launch—because `.claude/hooks/session-start.sh`
links the browser revision the client expects to the Chromium the image
carries. For driving the app outside the test suite, use that same build.

Chromium is pre-installed; do NOT run `playwright install`. Install
`playwright-core` into a scratch dir and launch with:

```js
chromium.launch({
  executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
});
```

(The bare `/opt/pw-browsers/chromium` path is a directory, not the binary —
glob for `chromium-*/chrome-linux/chrome` if the version bumped.)

## Routes worth driving

- `/#/en` — landing page
- `/#/en/story/{person_id}` — person story (e.g. `alan_turing`)
- `/#/{lang}/meta/{meta_story_id}` — meta story (e.g.
  `en/meta/computing_pioneers`, `de/meta/citizens_of_bamberg`)

The meta story page has scroll-driven sections (timeline scroll-proxy, network
scrollytelling), so drive them by scrolling the window, not by clicking.
For the network section, wait for `.network-svg:not(.hidden)` (layout settles
in the background), then scroll `.mnet-steps .step` elements into the
55%–75% viewport band to activate cards; `.node.dim` counts are a cheap
assertion for highlight state.

## Gotchas

- Map tiles/sprites (protomaps.github.io) may fail through the proxy —
  `AJAXError: Failed to fetch` console errors from the map are environmental,
  not a regression.
- Test both a desktop viewport and a narrow one (< 560px switches the network
  to compact sizing), and `de` alongside `en` for locale keys.
