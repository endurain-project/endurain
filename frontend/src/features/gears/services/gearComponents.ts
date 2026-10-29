import type {
  GearComponent,
  GearComponentDto,
  GearComponentInput,
  GearComponentTypeLists,
} from '@/features/gears/types'
import type { Schemas } from '@/types'

import { apiFetch } from '@/services/http'
import { ifMatchHeaders } from '@/services/ifMatch'

/**
 * Maps a raw `GearComponentRead` payload to the clean {@link GearComponent}
 * model — the single boundary where the backend wire format (snake_case,
 * nullable fields) is normalized so components never see the raw DTO.
 *
 * @param dto - Raw gear-component payload from the backend.
 * @returns The normalized gear-component model.
 */
export function mapGearComponent(dto: GearComponentDto): GearComponent {
  return {
    id: dto.id,
    userId: dto.user_id,
    gearId: dto.gear_id,
    type: dto.type,
    brand: dto.brand,
    model: dto.model,
    purchaseDate: dto.purchase_date ?? null,
    retiredDate: dto.retired_date ?? null,
    active: dto.active ?? true,
    expectedBaseUnits: dto.expected_kms ?? null,
    purchaseValue: dto.purchase_value ?? null,
    currentDistance: dto.current_distance ?? 0,
    currentTime: dto.current_time ?? 0,
    version: dto.version ?? 1,
  }
}

/**
 * Translates the clean form input into the backend's shared component wire
 * fields. `expectedBaseUnits` maps straight onto the backend's `expected_kms`
 * (which stores metres or seconds, not kilometres).
 *
 * @param input - The clean component input.
 * @returns The snake-cased fields common to create and update payloads.
 */
function toComponentWireFields(input: GearComponentInput) {
  return {
    type: input.type,
    brand: input.brand,
    model: input.model,
    purchase_date: input.purchaseDate,
    retired_date: input.retiredDate,
    active: input.active,
    expected_kms: input.expectedBaseUnits,
    purchase_value: input.purchaseValue,
  }
}

/**
 * Fetches the components attached to a gear, each enriched with accumulated
 * distance/time by the backend. The backend serves up to 200 per page, which one
 * gear's components never reach.
 *
 * @param gearId - The parent gear id.
 * @param signal - Optional abort signal for cancellation.
 * @returns The gear's components, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchGearComponents(
  gearId: number,
  signal?: AbortSignal,
): Promise<GearComponent[]> {
  const response = await apiFetch<Schemas['Page_GearComponentRead_']>(
    `/gears/${gearId}/components`,
    { signal },
  )
  return (response.items ?? []).map(mapGearComponent)
}

/**
 * Fetches the static component-type catalogues, grouped by gear family. The
 * lists never change at runtime, so callers cache this aggressively.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The component-type catalogues.
 * @throws {HttpError} When the request fails.
 */
export async function fetchGearComponentTypes(
  signal?: AbortSignal,
): Promise<GearComponentTypeLists> {
  return apiFetch<GearComponentTypeLists>('/gear-components/types', { signal })
}

/**
 * Creates a new gear component and returns the persisted record.
 *
 * @param input - The clean component input.
 * @returns The created component, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function createGearComponent(input: GearComponentInput): Promise<GearComponent> {
  const payload: Schemas['GearComponentCreate'] = {
    gear_id: input.gearId,
    ...toComponentWireFields(input),
  }
  const dto = await apiFetch<GearComponentDto>('/gear-components', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return mapGearComponent(dto)
}

/**
 * Updates an existing gear component and returns the persisted record.
 *
 * @param id - The component id to update.
 * @param input - The clean component input.
 * @param version - The row version the form was loaded at, for `If-Match`.
 * @returns The updated component, mapped to the clean model.
 * @throws {HttpError} When the request fails, including 412 when the copy is stale.
 */
export async function updateGearComponent(
  id: number,
  input: GearComponentInput,
  version: number,
): Promise<GearComponent> {
  // `purchase_date` cannot be cleared on the backend, so it is left out of the partial update when empty.
  const { purchase_date, ...fields } = toComponentWireFields(input)
  const payload: Schemas['GearComponentUpdate'] = {
    ...fields,
    ...(purchase_date === null ? {} : { purchase_date }),
  }
  const dto = await apiFetch<GearComponentDto>(`/gear-components/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
    headers: ifMatchHeaders(version),
  })
  return mapGearComponent(dto)
}

/**
 * Deletes a gear component by id. The backend replies `204 No Content`, so
 * there is no response body to map.
 *
 * @param id - The component id to delete.
 * @param version - The row version the caller read, for `If-Match`.
 * @throws {HttpError} When the request fails (`412` when the component changed since it was read).
 */
export async function deleteGearComponent(id: number, version: number): Promise<void> {
  await apiFetch<void>(`/gear-components/${id}`, {
    method: 'DELETE',
    headers: ifMatchHeaders(version),
    responseType: 'void',
  })
}
