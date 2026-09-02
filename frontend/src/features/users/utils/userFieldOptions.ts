/**
 * Shared option lists and helpers for the user-account edit forms. The admin
 * user form (`UserFormDialog`) and the self-service profile form
 * (`ProfileFormDialog`) edit the same underlying account fields, so the selector
 * choices, the numeric-range validator, and the unit-aware height resolution
 * live here once rather than being duplicated per form.
 */
import type { Schemas } from '@/types'

import { toNumberOrNull } from '@/utils/number'
import { feetAndInchesToCm } from '@/utils/units'
import type { Validator } from '@/utils/validators'

/** Maximum length for free-text account fields (name, username, email, city). */
export const TEXT_MAX = 250

/** Backend language codes offered in the preferred-language selector. */
export const LANGUAGE_CODES: ReadonlyArray<Schemas['Language']> = [
  'en',
  'pt-PT',
  'es',
  'ca',
  'de',
  'fr',
  'gl',
  'it',
  'nl',
  'sl',
  'sv',
  'zh-Hans',
  'zh-Hant',
  'pl',
  'tr',
  'uk',
  'ro',
  'nb',
  'da',
  'fi',
  'cs',
  'el',
  'hu',
  'bg',
  'hr',
  'sr',
  'sk',
  'lt',
  'lv',
  'et',
]

/**
 * Sorts the language codes alphabetically by their localized display label.
 *
 * @param label - Resolver returning the translated name for a language code.
 * @param locale - Active locale used for locale-aware comparison.
 * @returns The language codes ordered by display label.
 */
export function sortLanguageCodes(
  label: (code: Schemas['Language']) => string,
  locale: string,
): Schemas['Language'][] {
  return [...LANGUAGE_CODES].sort((a, b) => label(a).localeCompare(label(b), locale))
}

/** Gender options offered in the gender selector. */
export const GENDER_OPTIONS: ReadonlyArray<Schemas['Gender']> = ['male', 'female', 'unspecified']

/** First-day-of-week options offered in the selector. */
export const WEEKDAY_OPTIONS: ReadonlyArray<Schemas['WeekDay']> = [
  'sunday',
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
]

/** Currency options offered in the selector. */
export const CURRENCY_OPTIONS: ReadonlyArray<Schemas['Currency']> = ['euro', 'dollar', 'pound']

/**
 * Builds a validator for an optional whole-number field: an empty value passes,
 * otherwise it must fall within an inclusive `0..max` range.
 *
 * `value` is typed `number | null`, but `<input type="number">` with
 * `v-model.number` actually yields the raw string back when it can't parse to
 * a finite number (e.g. the field was just cleared), so it's coerced through
 * `toNumberOrNull` rather than compared directly.
 *
 * @param max - Largest allowed value.
 * @param message - Error message when out of range.
 * @returns A validator for the numeric field.
 */
export function numberRange(max: number, message: string): Validator<number | null> {
  return (value) => {
    const parsed = toNumberOrNull(value ?? '')
    if (parsed === null) {
      return null
    }
    return parsed >= 0 && parsed <= max ? null : message
  }
}

/** The unit-aware height fields shared by the account/profile edit forms. */
export interface HeightUnitFields {
  units: Schemas['Units']
  heightCm: number | null
  heightFeet: number | null
  heightInches: number | null
}

/**
 * Resolves the height in centimetres from whichever unit system is active.
 *
 * Each field is coerced through `toNumberOrNull` because `v-model.number`
 * leaves the raw (empty) string in place instead of `null` when a cleared
 * field fails to parse as a finite number.
 *
 * @param fields - The submitted height fields.
 * @returns Height in centimetres, or `null` when not provided.
 */
export function resolveHeightCm(fields: HeightUnitFields): number | null {
  if (fields.units === 'metric') {
    return toNumberOrNull(fields.heightCm ?? '')
  }
  const feet = toNumberOrNull(fields.heightFeet ?? '')
  const inches = toNumberOrNull(fields.heightInches ?? '')
  if (feet === null && inches === null) {
    return null
  }
  return feetAndInchesToCm(feet ?? 0, inches ?? 0)
}
