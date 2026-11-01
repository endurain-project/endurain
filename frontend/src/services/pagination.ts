import { apiFetch } from '@/services/http'

/** The envelope every paged list endpoint returns; only the fields the walk reads. */
interface PageDto<ItemDto> {
  items: ItemDto[]
  next?: number | null
}

/**
 * Reads a small paged list in full by following `next` until the last page. For
 * lists a screen shows whole (a user's goals or sessions), not for browse lists
 * that load a page at a time.
 *
 * @param path - The list endpoint path, without a query string.
 * @param params - Query parameters to send on every page; `page_number` is added.
 * @param signal - Optional abort signal for cancellation.
 * @returns The items of every page, in order.
 * @throws {HttpError} When a request fails.
 */
export async function fetchAllPages<ItemDto>(
  path: string,
  params: URLSearchParams = new URLSearchParams(),
  signal?: AbortSignal,
): Promise<ItemDto[]> {
  const items: ItemDto[] = []
  let page: number | null = 1
  while (page !== null) {
    params.set('page_number', String(page))
    const result: PageDto<ItemDto> | null = await apiFetch<PageDto<ItemDto> | null>(
      `${path}?${params.toString()}`,
      { signal },
    )
    items.push(...(result?.items ?? []))
    page = result?.next ?? null
  }
  return items
}
