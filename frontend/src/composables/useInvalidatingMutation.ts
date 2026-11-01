import { partialMatchKey, useMutation, useQueryClient, type QueryClient } from '@tanstack/vue-query'

/**
 * Invalidates a domain except the sub-trees a write cannot have changed, so a
 * broad prefix does not refetch static or per-item data that is on screen.
 *
 * @param client - The active query client.
 * @param queryKey - The domain prefix to invalidate (e.g. `queryKeys.gears.all()`).
 * @param excludedKeys - Key prefixes under `queryKey` that stay as they are.
 */
export function invalidateExcept(
  client: QueryClient,
  queryKey: readonly unknown[],
  excludedKeys: ReadonlyArray<readonly unknown[]>,
): Promise<void> {
  return client.invalidateQueries({
    queryKey,
    predicate: (query) =>
      !excludedKeys.some((excluded) => partialMatchKey(query.queryKey, excluded)),
  })
}

/** Options for {@link useInvalidatingMutation}. */
export interface InvalidatingMutationOptions<TData, TVariables> {
  /** Mutation identity key (used for dedupe/observability). */
  mutationKey: readonly unknown[]
  /** The async write to perform. */
  mutationFn: (variables: TVariables) => Promise<TData>
  /**
   * Query key to invalidate once the mutation settles. Defaults to
   * `mutationKey`. Pass a broader domain prefix (e.g. `queryKeys.gears.all()`)
   * when a write should cascade to lists, detail, and derived totals.
   */
  invalidateKey?: readonly unknown[]
  /**
   * Key prefixes under {@link invalidateKey} that the write cannot have changed
   * and that therefore keep their cache (see {@link invalidateExcept}).
   */
  excludeKeys?: ReadonlyArray<readonly unknown[]>
}

/**
 * Standard "write then invalidate" mutation — the reference pattern for
 * server-computed resources where an optimistic update would be guesswork
 * (the create/update/delete operations behind every CRUD domain). On settle it
 * invalidates the chosen domain key so every affected list, search, and detail
 * query refetches the server-authoritative state.
 *
 * Use the optimistic reference in `@/features/notifications/composables`
 * instead when the result is knowable client-side and instant feedback matters.
 *
 * @typeParam TData - The mutation's resolved value.
 * @typeParam TVariables - The mutation's input variables.
 * @param options - Mutation key, the write function, and the invalidation key.
 * @returns The TanStack Query mutation.
 */
export function useInvalidatingMutation<TData, TVariables>(
  options: InvalidatingMutationOptions<TData, TVariables>,
) {
  const client = useQueryClient()
  const invalidateKey = options.invalidateKey ?? options.mutationKey

  return useMutation<TData, Error, TVariables>({
    mutationKey: options.mutationKey,
    mutationFn: options.mutationFn,
    onSettled: () => {
      void invalidateExcept(client, invalidateKey, options.excludeKeys ?? [])
    },
  })
}
