import { toNumberOrNull } from './number'
import { isValidEmail } from './validation'

/**
 * A field validator: returns an error message when the value is invalid, or
 * `null` when it passes. Validators receive caller-supplied messages so the
 * framework stays i18n-agnostic — pass `t('...')` from the call site.
 *
 * @typeParam T - The field value type.
 */
export type Validator<T> = (value: T) => string | null

/**
 * Requires a non-empty value: rejects `null`/`undefined`, blank/whitespace
 * strings, and empty arrays.
 *
 * @typeParam T - The field value type.
 * @param message - Error message when the value is empty.
 * @returns A validator enforcing presence.
 */
export function required<T>(message: string): Validator<T> {
  return (value) => {
    if (value === null || value === undefined) {
      return message
    }
    if (typeof value === 'string' && value.trim().length === 0) {
      return message
    }
    if (Array.isArray(value) && value.length === 0) {
      return message
    }
    return null
  }
}

/**
 * Requires a string of at least `min` characters (after trimming).
 *
 * @param min - Minimum length.
 * @param message - Error message when too short.
 * @returns A string validator enforcing a minimum length.
 */
export function minLength(min: number, message: string): Validator<string> {
  return (value) => (value.trim().length < min ? message : null)
}

/**
 * Requires a string no longer than `max` characters (after trimming).
 *
 * @param max - Maximum length.
 * @param message - Error message when too long.
 * @returns A string validator enforcing a maximum length.
 */
export function maxLength(max: number, message: string): Validator<string> {
  return (value) => (value.trim().length > max ? message : null)
}

/**
 * Requires a syntactically valid email address. Empty values pass so this can
 * be combined with {@link required} when the field is mandatory.
 *
 * @param message - Error message when the value is not a valid email.
 * @returns A string validator enforcing email shape.
 */
export function email(message: string): Validator<string> {
  return (value) => (value.trim().length === 0 || isValidEmail(value) ? null : message)
}

/**
 * Requires the value to match a regular expression. Empty values pass so this
 * can be combined with {@link required}.
 *
 * @param regex - Pattern the value must match.
 * @param message - Error message when the value does not match.
 * @returns A string validator enforcing the pattern.
 */
export function pattern(regex: RegExp, message: string): Validator<string> {
  return (value) => (value.length === 0 || regex.test(value) ? null : message)
}

/**
 * Bounds an optional numeric field: an empty value passes, otherwise it must be
 * at least `min` and, when given, at most `max`.
 *
 * Accepts a number, a numeric string or `null`, because an `<input
 * type="number">` bound with `v-model.number` yields the raw string back when
 * it cannot parse, so the value is coerced through `toNumberOrNull`.
 *
 * @param min - Smallest allowed value.
 * @param max - Largest allowed value, or `undefined` for no upper bound.
 * @param message - Error message when out of range.
 * @returns A validator for the numeric field.
 */
export function numberBetween(
  min: number,
  max: number | undefined,
  message: string,
): Validator<string | number | null> {
  return (value) => {
    const parsed = toNumberOrNull(value ?? '')
    if (parsed === null) {
      return null
    }
    return parsed < min || (max !== undefined && parsed > max) ? message : null
  }
}

/**
 * Combines validators, returning the first failure (or `null` when all pass).
 * Order matters: list cheaper/foundational checks (e.g. `required`) first.
 *
 * @typeParam T - The field value type.
 * @param validators - Validators applied in order.
 * @returns A validator that short-circuits on the first error.
 */
export function compose<T>(...validators: Validator<T>[]): Validator<T> {
  return (value) => {
    for (const validate of validators) {
      const error = validate(value)
      if (error) {
        return error
      }
    }
    return null
  }
}
