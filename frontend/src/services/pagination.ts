import { apiFetch, type ApiFetchOptions } from '@/services/http'

/** The backend's maximum page size; every walk asks for full pages. */
export const MAX_PAGE_SIZE = 200

/** The envelope every paged list endpoint returns; only the fields the walk reads. */
interface PageDto<ItemDto> {
  items: ItemDto[] | null
  next?: number | null
}

/**
 * Reads a paged list in full by following `next` until the last page, keeping
 * each page's envelope so callers can read fields beside `items`. Pages are
 * requested at {@link MAX_PAGE_SIZE} unless `params` already sets `num_records`.
 *
 * @param path - The list endpoint path, without a query string.
 * @param params - Query parameters to send on every page; `page_number` is added.
 * @param init - Request options sent on every page (abort signal, credentials).
 * @returns The page envelopes, in order; an empty body ends the walk.
 * @throws {HttpError} When a request fails.
 */
export async function fetchAllPageEnvelopes<Page extends PageDto<unknown>>(
  path: string,
  params: URLSearchParams = new URLSearchParams(),
  init: ApiFetchOptions = {},
): Promise<Page[]> {
  const query = new URLSearchParams(params)
  if (!query.has('num_records')) {
    query.set('num_records', String(MAX_PAGE_SIZE))
  }
  const pages: Page[] = []
  let pageNumber: number | null = 1
  while (pageNumber !== null) {
    query.set('page_number', String(pageNumber))
    const result: Page | null = await apiFetch<Page | null>(`${path}?${query.toString()}`, init)
    if (result) {
      pages.push(result)
    }
    pageNumber = result?.next ?? null
  }
  return pages
}

/**
 * Reads a paged list in full as a flat item list. For lists a screen shows
 * whole (a user's goals or sessions), not for browse lists that load a page at
 * a time.
 *
 * @param path - The list endpoint path, without a query string.
 * @param params - Query parameters to send on every page; `page_number` is added.
 * @param init - Request options sent on every page (abort signal, credentials).
 * @returns The items of every page, in order.
 * @throws {HttpError} When a request fails.
 */
export async function fetchAllPages<ItemDto>(
  path: string,
  params: URLSearchParams = new URLSearchParams(),
  init: ApiFetchOptions = {},
): Promise<ItemDto[]> {
  const pages = await fetchAllPageEnvelopes<PageDto<ItemDto>>(path, params, init)
  return pages.flatMap((page) => page.items ?? [])
}
