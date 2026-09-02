/**
 * Number the figures and tables a report shows, in order, skipping the ones
 * it has nothing to show in. A report renders once per data set, and its
 * blocks are conditional, so the numbers are decided here rather than by a
 * counter in the template.
 *
 * @param {Array<[string, boolean]>} blocks - key and whether it is shown
 * @returns {Record<string, number>}
 */
export function numberBlocks(blocks) {
  const numbers = {};
  let n = 0;
  for (const [key, shown] of blocks) {
    if (shown) {
      n += 1;
      numbers[key] = n;
    }
  }
  return numbers;
}
