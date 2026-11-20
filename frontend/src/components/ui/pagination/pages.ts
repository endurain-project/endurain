/** Sentinel marking an elided range of page numbers in {@link paginationItems}. */
export const PAGINATION_ELLIPSIS = '\u2026'

/**
 * Builds the items a pager renders: page numbers interleaved with
 * {@link PAGINATION_ELLIPSIS} markers. Every page when
 * there are five or fewer, otherwise the first and last pages plus a sliding
 * window around the current page.
 *
 * @param current - The current 1-based page.
 * @param total - The total number of pages (at least 1).
 * @returns The ordered page numbers and ellipsis markers to render.
 */
export function paginationItems(
  current: number,
  total: number,
): Array<number | typeof PAGINATION_ELLIPSIS> {
  if (total <= 5) {
    return Array.from({ length: total }, (_, index) => index + 1)
  }
  if (current <= 2) {
    return [1, 2, 3, PAGINATION_ELLIPSIS, total]
  }
  if (current >= total - 1) {
    return [1, PAGINATION_ELLIPSIS, total - 2, total - 1, total]
  }
  return [1, PAGINATION_ELLIPSIS, current - 1, current, current + 1, PAGINATION_ELLIPSIS, total]
}
