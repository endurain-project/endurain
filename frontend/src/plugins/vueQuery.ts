import {
  MutationCache,
  QueryCache,
  QueryClient,
  VueQueryPlugin,
  type VueQueryPluginOptions,
} from '@tanstack/vue-query'

import { useTelemetry } from '@/composables/useTelemetry'
import { HttpError } from '@/services/http'

/**
 * Default query retry policy: retry at most once, and only a transient failure.
 * A non-HTTP failure (network error, timeout) or a 5xx other than 501 is retried;
 * a deliberate abort and every 4xx, including 429, is not.
 *
 * @param failureCount - Number of failures so far for this query.
 * @param error - The error the query function threw.
 * @returns `true` when the query should be retried.
 */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (failureCount >= 1) return false
  if (error instanceof HttpError) return error.status >= 500 && error.status !== 501
  return !(error instanceof DOMException && error.name === 'AbortError')
}

/**
 * Shared query client. Server state (caching, dedupe, background refetch,
 * invalidation) flows through TanStack Query; Pinia stays client-only.
 *
 * Cache-level `onError` handlers forward every failed query and mutation to the
 * telemetry adapter so observability is centralised rather than repeated in each
 * call site. Only the (token-free) query/mutation key is attached as context;
 * raw variables and responses are never forwarded.
 */
export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error, query) => {
      useTelemetry().captureError(error, { scope: 'query', queryKey: query.queryKey })
    },
  }),
  mutationCache: new MutationCache({
    onError: (error, _variables, _context, mutation) => {
      useTelemetry().captureError(error, {
        scope: 'mutation',
        mutationKey: mutation.options.mutationKey,
      })
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: shouldRetryQuery,
      refetchOnWindowFocus: false,
    },
  },
})

export const vueQueryOptions: VueQueryPluginOptions = { queryClient }

export { VueQueryPlugin }
