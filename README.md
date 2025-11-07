# Life Data Stories Viewer

A mobile-first Svelte + Vite experience that presents Alan Turing's life events as full-height, scroll-snapped slides sourced from `data/alan_turing_life_events.json`.

## Getting Started

```powershell
npm install
npm run dev -- --open
```

- `npm run build` generates a production bundle in `dist/`.
- `npm run preview` serves the production build locally.

## Generating Data Assets

Both dataset and styling generators rely on the OpenAI API. Set `OPENAI_API_KEY` before running the scripts.

```powershell
python scripts/generate_person_dataset.py "Ada Lovelace"
python scripts/generate_person_style.py "Ada Lovelace"
```

By default the scripts write to `data/people/` and `data/person_styles.json`, updating the shared registry files as needed.
