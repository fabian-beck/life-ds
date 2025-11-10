# ImageViewer Component

A reusable full-screen image viewer component with pan and zoom capabilities.

## Features

- **Full-screen viewing**: Images are displayed as large as the screen allows
- **Mouse wheel zoom**: Scroll to zoom in/out, with zoom centered on cursor position
- **Pan support**: Click and drag to pan around zoomed images
- **Touch gestures**:
  - Pinch to zoom on touch devices
  - Drag to pan with single touch
- **Double-click/tap to zoom**: Quick zoom in/out toggle
- **Keyboard shortcuts**:
  - `Escape`: Close viewer
  - `R`: Reset view to default
  - `+`/`=`: Zoom in
  - `-`: Zoom out
- **Reset button**: Return to original view state
- **Responsive design**: Optimized for both desktop and mobile

## Usage

```svelte
<script>
  import ImageViewer from "./ImageViewer.svelte";

  let imageData = {
    url: "path/to/image.jpg",
    caption: "Optional caption",
    source: "Optional source URL"
  };

  let showViewer = false;

  function closeViewer() {
    showViewer = false;
  }
</script>

{#if showViewer}
  <ImageViewer image={imageData} onClose={closeViewer} />
{/if}
```

## Props

- `image`: Object with the following properties:
  - `url` (string, required): Image URL
  - `caption` (string, optional): Image caption to display
  - `source` (string, optional): Source URL for attribution
- `onClose`: Function to call when the viewer is closed

## Implementation Details

- Uses CSS transforms for smooth pan/zoom
- Touch events are properly handled to support multi-touch gestures
- Prevents excessive zooming (min: 0.5x, max: 10x)
- Accessible with keyboard navigation
- Non-blocking UI with visual hints for desktop users
