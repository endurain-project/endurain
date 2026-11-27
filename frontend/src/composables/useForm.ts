import { computed, reactive, readonly, ref, shallowRef } from 'vue'

import type { Validator } from '@/utils/validators'

/** Per-field validators keyed by form field name. */
export type FormValidators<Values> = {
  [K in keyof Values]?: Validator<Values[K]>
}

/** Per-field error messages, present only for fields that currently fail. */
export type FormErrors<Values> = Partial<Record<keyof Values, string>>

/** Per-field "has been interacted with" flags. */
export type FormTouched<Values> = Partial<Record<keyof Values, boolean>>

/** Options for {@link useForm}. */
export interface UseFormOptions<Values extends object> {
  /** Initial field values; also the baseline for `isDirty` and `reset()`. */
  initialValues: Values
  /** Optional per-field validators. Omit a field to leave it unvalidated. */
  validators?: FormValidators<Values>
  /**
   * Submit handler invoked with the current values once validation passes.
   * Throwing here surfaces the error message via `submitError`; handle errors
   * inside the callback (e.g. map to an i18n message) when you need control.
   */
  onSubmit: (values: Values) => void | Promise<void>
}

/**
 * Headless, dependency-free form state for Vue 3. Owns values, per-field
 * validation, touched/dirty tracking, server-error injection, and submit
 * lifecycle — so the ~17 settings forms and the many health/gear/goal forms in
 * scope share one tested mechanism instead of hand-rolling refs each time.
 *
 * It is intentionally i18n-agnostic: validators carry caller-supplied messages
 * (pass `t('...')`), and it pairs with the `FormField` component for the a11y
 * wiring (label association, `aria-live` errors). Bind controls to the returned
 * reactive `values`; gate the submit button on `isValid`.
 *
 * @typeParam Values - The form's field shape.
 * @param options - Initial values, optional validators, and the submit handler.
 * @returns Reactive form state plus submit/blur/validation/reset helpers.
 */
export function useForm<Values extends object>(options: UseFormOptions<Values>) {
  const { initialValues, validators, onSubmit } = options

  const values = reactive({ ...initialValues }) as Values
  const baseline = shallowRef<Values>({ ...initialValues })
  const errors = ref<FormErrors<Values>>({})
  const touched = ref<FormTouched<Values>>({})
  const isSubmitting = ref(false)
  const submitError = ref<string | null>(null)

  /**
   * Runs a single field's validator without mutating state.
   *
   * @param key - Field to validate.
   * @returns The error message, or `null` when valid or unvalidated.
   */
  function runValidator<K extends keyof Values>(key: K): string | null {
    const validate = validators?.[key]
    return validate ? validate(values[key]) : null
  }

  /**
   * Sets or clears a field's error without using dynamic `delete`.
   *
   * @param key - Field whose error to set.
   * @param error - The error message, or `null` to clear it.
   */
  function setFieldError<K extends keyof Values>(key: K, error: string | null): void {
    const next: FormErrors<Values> = {}
    for (const existing of Object.keys(errors.value) as (keyof Values)[]) {
      if (existing !== key) {
        next[existing] = errors.value[existing]
      }
    }
    if (error) {
      next[key] = error
    }
    errors.value = next
  }

  /** Whether every validated field currently passes (pure; no side effects). */
  const isValid = computed(() => {
    if (!validators) {
      return true
    }
    return (Object.keys(validators) as (keyof Values)[]).every((key) => runValidator(key) === null)
  })

  /** Whether any field differs from the baseline (the initial values, or the last `markPristine()`). */
  const isDirty = computed(() =>
    (Object.keys(initialValues) as (keyof Values)[]).some(
      (key) => values[key] !== baseline.value[key],
    ),
  )

  /**
   * Validates one field and records its error/touched state.
   *
   * @param key - Field to validate.
   * @returns The error message, or `null` when valid.
   */
  function validateField<K extends keyof Values>(key: K): string | null {
    const error = runValidator(key)
    setFieldError(key, error)
    return error
  }

  /**
   * Validates every field and replaces the error map.
   *
   * @returns Whether the whole form is valid.
   */
  function validate(): boolean {
    const nextErrors: FormErrors<Values> = {}
    if (validators) {
      for (const key of Object.keys(validators) as (keyof Values)[]) {
        const error = runValidator(key)
        if (error) {
          nextErrors[key] = error
        }
      }
    }
    errors.value = nextErrors
    return Object.keys(nextErrors).length === 0
  }

  /**
   * Marks a field touched and validates it. Wire to a control's `blur` event so
   * errors appear only after the user has interacted with the field.
   *
   * @param key - The field that lost focus.
   */
  function handleBlur<K extends keyof Values>(key: K): void {
    touched.value = { ...touched.value, [key]: true }
    validateField(key)
  }

  /**
   * Sets a field's value, re-validating it if it has already been touched.
   *
   * @param key - Field to update.
   * @param value - New value.
   */
  function setFieldValue<K extends keyof Values>(key: K, value: Values[K]): void {
    values[key] = value
    if (touched.value[key]) {
      validateField(key)
    }
  }

  /**
   * Merges server-provided field errors (e.g. from a `422` response) into the
   * error map so backend validation can render inline beside the field.
   *
   * @param serverErrors - Field-keyed error messages from the backend.
   */
  function setErrors(serverErrors: FormErrors<Values>): void {
    errors.value = { ...errors.value, ...serverErrors }
  }

  /**
   * Makes the current values the `isDirty` baseline. Call it after seeding an
   * edit form from a record so an untouched form reads as clean.
   */
  function markPristine(): void {
    baseline.value = { ...values }
  }

  /** Restores initial values and clears all errors, touched, and submit state. */
  function reset(): void {
    Object.assign(values, { ...initialValues })
    baseline.value = { ...initialValues }
    errors.value = {}
    touched.value = {}
    submitError.value = null
  }

  /**
   * Validates the whole form (marking validated fields touched) and, when
   * valid, runs `onSubmit`. A thrown submit error is captured into
   * `submitError` rather than rethrown, so templates can display it inline.
   */
  async function handleSubmit(): Promise<void> {
    if (validators) {
      const allTouched: FormTouched<Values> = { ...touched.value }
      for (const key of Object.keys(validators) as (keyof Values)[]) {
        allTouched[key] = true
      }
      touched.value = allTouched
    }
    submitError.value = null
    if (!validate()) {
      return
    }
    isSubmitting.value = true
    try {
      await onSubmit({ ...values } as Values)
    } catch (error) {
      submitError.value = error instanceof Error ? error.message : String(error)
    } finally {
      isSubmitting.value = false
    }
  }

  return {
    /** Reactive field values — bind controls with `v-model`. */
    values,
    /** Per-field error messages (read-only). */
    errors: readonly(errors),
    /** Per-field touched flags (read-only). */
    touched: readonly(touched),
    /** Whether a submit is in flight (read-only). */
    isSubmitting: readonly(isSubmitting),
    /** Last submit error message, or `null` (read-only). */
    submitError: readonly(submitError),
    /** Whether all validated fields currently pass. */
    isValid,
    /** Whether any field differs from the baseline (initial values or last `markPristine()`). */
    isDirty,
    markPristine,
    handleSubmit,
    handleBlur,
    validateField,
    validate,
    setFieldValue,
    setErrors,
    reset,
  }
}
