<script>
  // A figure of the report: the drawing, and under it a numbered caption that
  // reads the same as a table's. `wide` lets a drawing take the page rather
  // than the measure.
  const { n, caption, wide = false, children } = $props();
</script>

<figure class="figure" class:figure-wide={wide}>
  <div class="figure-body">
    {@render children?.()}
  </div>
  <figcaption class="cap">
    <span class="cap-no">Figure {n}.</span>
    {caption}
  </figcaption>
</figure>
