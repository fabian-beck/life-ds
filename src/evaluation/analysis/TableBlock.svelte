<script>
  // A table of the report, captioned above the way a table is in print.
  const { n, caption, wide = false, children } = $props();
</script>

<div class="table-block" class:table-wide={wide}>
  <p class="cap cap-table">
    <span class="cap-no">Table {n}.</span>
    {caption}
  </p>
  <div class="table-scroll">
    {@render children?.()}
  </div>
</div>
