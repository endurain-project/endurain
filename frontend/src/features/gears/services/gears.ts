import type {
  Gear,
  GearDetail,
  GearDetailDto,
  GearDto,
  GearInput,
  GearsPage,
} from '@/features/gears/types'
import type { Schemas } from '@/types'

import { apiFetch, HttpError } from '@/services/http'
import { ifMatchHeaders } from '@/services/ifMatch'

/** Largest page the list endpoint serves; the filtered lookups fetch one such page. */
const MAX_NUM_RECORDS = 200

/** Pagination + filter input for a gears list request. */
export interface GearsListParams {
  /** 1-based page number. */
  page: number
  /** Page size (records per page). */
  numRecords: number
  /** Whether inactive gears are included in the results. */
  showInactive: boolean
}

/**
 * Maps a raw `GearRead` payload to the clean {@link Gear} model — the single
 * boundary where the backend wire format (snake_case, nullable fields) is
 * normalized so components never see the raw DTO.
 *
 * @param dto - Raw gear payload from the backend.
 * @returns The normalized gear model.
 */
export function mapGear(dto: GearDto): Gear {
  return {
    id: dto.id,
    userId: dto.user_id,
    gearType: dto.gear_type,
    nickname: dto.nickname,
    brand: dto.brand ?? null,
    model: dto.model ?? null,
    active: dto.active ?? true,
    createdAt: dto.created_at ?? null,
    initialKms: dto.initial_kms ?? null,
    purchaseValue: dto.purchase_value ?? null,
    stravaGearId: dto.strava_gear_id ?? null,
    garminConnectGearId: dto.garminconnect_gear_id ?? null,
    version: dto.version ?? 1,
  }
}

/**
 * Maps a raw `GearDetailRead` payload to the clean {@link GearDetail} model,
 * adding the computed totals on top of the base gear fields.
 *
 * @param dto - Raw gear detail payload from the backend.
 * @returns The normalized gear detail model.
 */
export function mapGearDetail(dto: GearDetailDto): GearDetail {
  return {
    ...mapGear(dto),
    totalDistance: dto.total_distance,
    totalTime: dto.total_time,
    totalComponentsCost: dto.total_components_cost,
  }
}

/**
 * Translates the clean form input into the backend's shared gear wire fields.
 * Integration-managed ids (Strava/Garmin) are intentionally omitted.
 *
 * @param input - The clean gear input.
 * @returns The snake-cased fields common to create and update payloads.
 */
function toGearWireFields(input: GearInput) {
  return {
    nickname: input.nickname,
    gear_type: input.gearType,
    brand: input.brand,
    model: input.model,
    active: input.active,
    created_at: input.createdAt,
    initial_kms: input.initialKms,
    purchase_value: input.purchaseValue,
  }
}

/**
 * Fetches one page of the authenticated user's gears.
 *
 * @param params - Page number, size, and the show-inactive filter.
 * @param signal - Optional abort signal so TanStack Query can cancel the
 *   request on unmount or invalidation.
 * @returns The page's gears (mapped) plus the total record count.
 * @throws {HttpError} When the request fails.
 */
export async function fetchGears(
  { page, numRecords, showInactive }: GearsListParams,
  signal?: AbortSignal,
): Promise<GearsPage> {
  const params = new URLSearchParams({
    page_number: String(page),
    num_records: String(numRecords),
    show_inactive: String(showInactive),
  })
  const response = await apiFetch<Schemas['Page_GearRead_']>(`/gears?${params.toString()}`, {
    signal,
  })
  return {
    records: (response.items ?? []).map(mapGear),
    total: response.total,
  }
}

/**
 * Fetches up to one maximum-size page of the user's gears matching the given list filters.
 *
 * @param filters - Query-string filters (`gear_type`, `nickname_contains`).
 * @param signal - Optional abort signal for cancellation.
 * @returns The matching gears, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
async function fetchGearsMatching(
  filters: Record<string, string>,
  signal?: AbortSignal,
): Promise<Gear[]> {
  const params = new URLSearchParams({ num_records: String(MAX_NUM_RECORDS), ...filters })
  const response = await apiFetch<Schemas['Page_GearRead_']>(`/gears?${params.toString()}`, {
    signal,
  })
  return (response.items ?? []).map(mapGear)
}

/**
 * Searches the user's gears whose nickname contains the given term.
 *
 * @param nickname - The search term.
 * @param signal - Optional abort signal for cancellation.
 * @returns The matching gears, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function searchGearsByNickname(
  nickname: string,
  signal?: AbortSignal,
): Promise<Gear[]> {
  return fetchGearsMatching({ nickname_contains: nickname }, signal)
}

/**
 * Fetches a single gear with computed stats, or `null` when it does not exist.
 *
 * @param id - The gear id.
 * @param signal - Optional abort signal for cancellation.
 * @returns The gear detail, or `null` when not found.
 * @throws {HttpError} When the request fails.
 */
export async function fetchGearById(id: number, signal?: AbortSignal): Promise<GearDetail | null> {
  try {
    const dto = await apiFetch<GearDetailDto | null>(`/gears/${id}`, { signal })
    return dto ? mapGearDetail(dto) : null
  } catch (error) {
    if (error instanceof HttpError && error.status === 404) return null
    throw error
  }
}

/**
 * Fetches all of the user's gears of a single gear type (e.g. all shoes), used
 * to populate the per-activity default-gear selectors.
 *
 * @param gearType - The numeric gear type (see `GEAR_TYPE`).
 * @param signal - Optional abort signal for cancellation.
 * @returns The matching gears, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchGearsByType(gearType: number, signal?: AbortSignal): Promise<Gear[]> {
  return fetchGearsMatching({ gear_type: String(gearType) }, signal)
}

/**
 * Creates a new gear and returns the persisted record.
 *
 * @param input - The clean gear input.
 * @returns The created gear, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function createGear(input: GearInput): Promise<Gear> {
  const payload: Schemas['GearCreateRequest'] = toGearWireFields(input)
  const dto = await apiFetch<GearDto>('/gears', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return mapGear(dto)
}

/**
 * Updates an existing gear and returns the persisted record.
 *
 * `created_at` and `initial_kms` cannot be cleared on the backend, so they are left out of
 * the partial update when empty.
 *
 * @param id - The gear id to update.
 * @param input - The clean gear input.
 * @param version - The row version the form was loaded at, for `If-Match`.
 * @returns The updated gear, mapped to the clean model.
 * @throws {HttpError} When the request fails, including 412 when the copy is stale.
 */
export async function updateGear(id: number, input: GearInput, version: number): Promise<Gear> {
  const { created_at, initial_kms, ...fields } = toGearWireFields(input)
  const payload: Schemas['GearUpdate'] = {
    ...fields,
    ...(created_at === null ? {} : { created_at }),
    ...(initial_kms === null ? {} : { initial_kms }),
  }
  const dto = await apiFetch<GearDto>(`/gears/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
    headers: ifMatchHeaders(version),
  })
  return mapGear(dto)
}

/**
 * Deletes a gear by id. The backend replies `204 No Content`, so there is no
 * response body to map.
 *
 * @param id - The gear id to delete.
 * @param version - The row version the caller read, for `If-Match`.
 * @throws {HttpError} When the request fails (`412` when the gear changed since it was read).
 */
export async function deleteGear(id: number, version: number): Promise<void> {
  await apiFetch<void>(`/gears/${id}`, {
    method: 'DELETE',
    headers: ifMatchHeaders(version),
    responseType: 'void',
  })
}
