/** Freshness window for mutable gear reads; gear writes and sync events invalidate them. */
export const GEAR_QUERY_STALE_TIME_MS = 60_000
