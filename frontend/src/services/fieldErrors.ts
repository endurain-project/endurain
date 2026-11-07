import type { FormErrors } from '@/composables/useForm'
import { HttpError } from './http'

/** Translation keys for the pydantic error types the API emits; any other type is `invalid`. */
const MESSAGE_KEY_BY_TYPE: Readonly<Record<string, string>> = {
  missing: 'required',
  string_too_short: 'tooShort',
  too_short: 'tooShort',
  string_too_long: 'tooLong',
  too_long: 'tooLong',
  less_than: 'tooLarge',
  less_than_equal: 'tooLarge',
  greater_than: 'tooSmall',
  greater_than_equal: 'tooSmall',
  string_pattern_mismatch: 'invalidFormat',
}

/**
 * Converts a snake_case API field name to its camelCase form key.
 *
 * @param field - The API field name.
 * @returns The camelCase name.
 */
function snakeToCamel(field: string): string {
  return field.replace(/_([a-z0-9])/g, (_, char: string) => char.toUpperCase())
}

/**
 * Shows a 422 response's per-field failures beside the form fields they name. A known pydantic error
 * type maps to a translated message; any other failure shows the server's own message, or the
 * generic translated text when it has none.
 *
 * @param error - The error a write rejected with.
 * @param setErrors - The form's `setErrors`.
 * @param t - The translate function.
 * @param keys - The form's field keys; a failure for any other field is not mapped.
 * @param map - API field names whose form key is not their camelCase form.
 * @returns Whether at least one failure was mapped to a form field.
 */
export function applyServerFieldErrors<Values extends object>(
  error: unknown,
  setErrors: (errors: FormErrors<Values>) => void,
  t: (key: string) => string,
  keys: readonly (keyof Values & string)[],
  map: Readonly<Record<string, keyof Values & string>> = {},
): boolean {
  if (!(error instanceof HttpError) || error.status !== 422) {
    return false
  }
  const mapped: FormErrors<Values> = {}
  let any = false
  for (const failure of error.errors) {
    const [scope, name] = failure.field.split('.')
    if (scope !== 'body' || !name) {
      continue
    }
    const key = map[name] ?? snakeToCamel(name)
    const field = keys.find((candidate) => candidate === key)
    if (field && !(field in mapped)) {
      const typeKey = MESSAGE_KEY_BY_TYPE[failure.type]
      mapped[field] = typeKey
        ? t(`app.fieldError.${typeKey}`)
        : failure.message.trim() || t('app.fieldError.invalid')
      any = true
    }
  }
  if (any) {
    setErrors(mapped)
  }
  return any
}
