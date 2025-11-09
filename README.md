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

### Python Dependencies

Install the required Python packages:

```powershell
pip install -r requirements.txt
```

The scripts require:

- `openai` - OpenAI API client with structured outputs support
- `requests` - HTTP library for Wikipedia API
- `pydantic` - Data validation for structured outputs

### Running the Generators

```powershell
python scripts/generate_person_dataset.py "Ada Lovelace"
python scripts/generate_person_style.py "Ada Lovelace"
```

The dataset generator uses `gpt-4o-mini` by default. To use a different model:

```powershell
python scripts/generate_person_dataset.py "Ada Lovelace" --model gpt-4o-2024-08-06
```

By default the scripts write to `data/people/` and `data/person_styles.json`, updating the shared registry files as needed.

### Event Images

The dataset generator now automatically includes relevant images for events when meaningful images are available from Wikipedia. Each image includes metadata such as a caption and source link. Images are stored in an optional `images` array within each event:

```json
{
  "date": "1842",
  "title": "Translates Menabrea's paper on the Analytical Engine",
  "images": [
    {
      "url": "https://upload.wikimedia.org/wikipedia/commons/c/cf/Diagram_for_the_computation_of_Bernoulli_numbers.jpg",
      "caption": "Diagram of an algorithm for the Analytical Engine for computing Bernoulli numbers",
      "source": "https://commons.wikimedia.org/wiki/File:Diagram_for_the_computation_of_Bernoulli_numbers.jpg"
    }
  ]
}
```

The UI displays these images as small thumbnails in the top-right corner of each event slide. Click on any thumbnail to view the enlarged image with its caption and a direct link to the Wikimedia Commons source page.
