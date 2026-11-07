/**
 * Height unit conversions shared by forms that capture height in either the
 * metric (centimetres) or imperial (feet/inches) system. The backend stores
 * height in centimetres, so imperial input is converted before submission.
 */

/** Feet and inches breakdown of a metric height. */
export interface FeetInches {
  feet: number
  inches: number
}

/**
 * Converts centimetres to whole feet and rounded inches.
 *
 * Rounds to the nearest whole inch first, then splits into feet and inches, so
 * a value that rounds up to 12 inches (e.g. 182 cm) carries over to the next
 * foot (6'0") rather than producing an out-of-range 5'12".
 *
 * @param cm - Height in centimetres.
 * @returns The equivalent feet and inches.
 */
export function cmToFeetInches(cm: number): FeetInches {
  const totalInches = Math.round(cm / 2.54)
  return {
    feet: Math.floor(totalInches / 12),
    inches: totalInches % 12,
  }
}

/**
 * Converts feet and inches to whole centimetres.
 *
 * @param feet - Feet component of the height.
 * @param inches - Inches component of the height.
 * @returns The equivalent height in centimetres, rounded to the nearest cm.
 */
export function feetAndInchesToCm(feet: number, inches: number): number {
  const totalInches = feet * 12 + inches
  return Math.round(totalInches * 2.54)
}

/** Kilometres in one mile, used for distance conversions. */
const KM_PER_MILE = 1.609344

/**
 * Converts kilometres to miles.
 *
 * @param km - Distance in kilometres.
 * @returns The equivalent distance in miles.
 */
export function kmToMiles(km: number): number {
  return km / KM_PER_MILE
}

/**
 * Converts miles to kilometres.
 *
 * @param miles - Distance in miles.
 * @returns The equivalent distance in kilometres.
 */
export function milesToKm(miles: number): number {
  return miles * KM_PER_MILE
}

/** Pounds in one kilogram, used for weight conversions. */
const LBS_PER_KG = 2.2046226218

/**
 * Converts kilograms to pounds.
 *
 * @param kg - Mass in kilograms.
 * @returns The equivalent mass in pounds.
 */
export function kgToLbs(kg: number): number {
  return kg * LBS_PER_KG
}

/**
 * Converts pounds to kilograms.
 *
 * @param lbs - Mass in pounds.
 * @returns The equivalent mass in kilograms.
 */
export function lbsToKg(lbs: number): number {
  return lbs / LBS_PER_KG
}

/** US fluid ounces in one millilitre, used for volume conversions. */
const FL_OZ_PER_ML = 0.0338140227

/**
 * Converts millilitres to US fluid ounces.
 *
 * @param ml - Volume in millilitres.
 * @returns The equivalent volume in US fluid ounces.
 */
export function mlToFlOz(ml: number): number {
  return ml * FL_OZ_PER_ML
}

/**
 * Converts US fluid ounces to millilitres.
 *
 * @param flOz - Volume in US fluid ounces.
 * @returns The equivalent volume in millilitres.
 */
export function flOzToMl(flOz: number): number {
  return flOz / FL_OZ_PER_ML
}

/**
 * Resolves the base-unit value to send for a unit-converted form field. A field the user has not
 * edited still holds the rounded display text it was seeded with; converting that back would drift
 * from the stored value, so the stored value is kept. An edited field is converted.
 *
 * @param current - The field's current input.
 * @param seeded - The display text the field was seeded with from `stored`.
 * @param stored - The value the record holds, or `null`/`undefined` when there is none.
 * @param convert - Converts the current input to the base unit.
 * @returns The stored value for an untouched field, otherwise the converted input.
 */
export function baseValueUnlessEdited(
  current: string | number,
  seeded: string,
  stored: number | null | undefined,
  convert: (current: string | number) => number,
): number {
  return stored != null && String(current).trim() === seeded ? stored : convert(current)
}
