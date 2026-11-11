import type { InjectionKey } from 'vue'
import { computed, inject, provide, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  ServerSettings,
  ServerSettingsFormValues,
  TileMapsTemplate,
} from '@/features/serverSettings/types'
import type { IdpReauth, StepUpInput } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'
import type { Validator } from '@/utils/validators'

import { useForm } from '@/composables/useForm'
import { useToasts } from '@/composables/useToasts'
import { isStepUpFailed, useIdpReauthChallenge } from '@/features/security/composables/useIdpStepUp'
import { useResumeOnce } from '@/features/security/composables/useAdminStepUp'
import { useSettingsStepUpResume } from '@/features/serverSettings/composables/useMailStepUpResume'
import { useUpdateServerSettingsMutation } from '@/features/serverSettings/composables/useServerSettings'
import { FIELD_TABS, type SettingsTab } from '@/features/serverSettings/settingsTabs'
import { HttpError } from '@/services/http'

/** Sentinel id for the "custom" (manually edited) tile server. */
export const CUSTOM_TEMPLATE = 'custom'
/** Public hosts each geocoding service uses when none is set; shown as the host placeholder. */
const GEOCODING_DEFAULT_HOSTS: Record<string, string> = {
  nominatim: 'nominatim.openstreetmap.org',
  photon: 'photon.komoot.io',
}
/** Highest accepted geocoding rate limit (requests per second). */
const MAX_GEOCODING_RATE_LIMIT = 100
/** Accepted ranges of the session policy numbers (mirrors the backend bounds). */
const IDLE_HOURS_RANGE = { min: 1, max: 8760 } as const
const ABSOLUTE_HOURS_RANGE = { min: 1, max: 8760 } as const
const ACCESS_MINUTES_RANGE = { min: 1, max: 1440 } as const
const REFRESH_DAYS_RANGE = { min: 1, max: 365 } as const
const API_KEY_DAYS_RANGE = { min: 1, max: 3650 } as const
const RETENTION_DAYS_RANGE = { min: 0, max: 3650 } as const
/** Accepted audit trail retention besides 0 (keep everything): the database-side floor to the substrate maximum. */
const AUDIT_RETENTION_DAYS_RANGE = { min: 30, max: 36500 } as const
/** The write-only API key fields; a draft kept across the identity-provider sign-in never holds them. */
const SECRET_FIELDS = ['tileserverApiKey', 'geocodingApiKey'] as const
/** Placeholders every valid tile URL template must contain. */
const TILE_PLACEHOLDERS = ['{z}', '{x}', '{y}'] as const

/**
 * Projects the loaded settings onto the form-editable subset. `id` and
 * `loginPhotoSet` are intentionally excluded: they round-trip from the freshest
 * server state at save time, never from a stale form value. The API keys start
 * empty: the backend never returns them, and an empty field keeps the stored one.
 *
 * @param settings - The loaded server settings.
 * @returns The editable form values.
 */
function toFormValues(settings: ServerSettings): ServerSettingsFormValues {
  return {
    units: settings.units,
    currency: settings.currency,
    numRecordsPerPage: settings.numRecordsPerPage,
    publicShareableLinks: settings.publicShareableLinks,
    publicShareableLinksUserInfo: settings.publicShareableLinksUserInfo,
    signupEnabled: settings.signupEnabled,
    signupSsoEnabled: settings.signupSsoEnabled,
    signupRequireAdminApproval: settings.signupRequireAdminApproval,
    signupRequireEmailVerification: settings.signupRequireEmailVerification,
    ssoEnabled: settings.ssoEnabled,
    localLoginEnabled: settings.localLoginEnabled,
    ssoAutoRedirect: settings.ssoAutoRedirect,
    tileserverUrl: settings.tileserverUrl,
    tileserverAttribution: settings.tileserverAttribution,
    tileserverApiKey: '',
    removeTileserverApiKey: false,
    tileserverRegenerateThumbnailsOnChange: settings.tileserverRegenerateThumbnailsOnChange,
    mapBackgroundColor: settings.mapBackgroundColor,
    passwordLengthRegularUsers: settings.passwordLengthRegularUsers,
    passwordLengthAdminUsers: settings.passwordLengthAdminUsers,
    passwordBreachCheckEnabled: settings.passwordBreachCheckEnabled,
    requireMfa: settings.requireMfa,
    geocodingService: settings.geocodingService,
    geocodingHost: settings.geocodingHost ?? '',
    geocodingUseHttps: settings.geocodingUseHttps,
    geocodingRateLimit: String(settings.geocodingRateLimit),
    geocodingApiKey: '',
    removeGeocodingApiKey: false,
    sessionIdleTimeoutEnabled: settings.sessionIdleTimeoutEnabled,
    sessionIdleTimeoutHours: String(settings.sessionIdleTimeoutHours),
    sessionAbsoluteTimeoutHours: String(settings.sessionAbsoluteTimeoutHours),
    accessTokenExpireMinutes: String(settings.accessTokenExpireMinutes),
    refreshTokenExpireDays: String(settings.refreshTokenExpireDays),
    apiKeyMaxLifetimeDays: String(settings.apiKeyMaxLifetimeDays),
    readNotificationRetentionDays: String(settings.readNotificationRetentionDays),
    auditRetentionDays: String(settings.auditRetentionDays),
    auditLegalHold: settings.auditLegalHold,
  }
}

/**
 * Validates a whole number within an inclusive range.
 *
 * @param range - The inclusive bounds.
 * @param message - Error when the value is not a whole number in range.
 * @returns A validator for the numeric field.
 */
function integerRangeValidator(
  range: { readonly min: number; readonly max: number },
  message: string,
): Validator<string> {
  return (value) => {
    const number = Number(value.trim())
    return value.trim() !== '' &&
      Number.isInteger(number) &&
      number >= range.min &&
      number <= range.max
      ? null
      : message
  }
}

/**
 * Validates the geocoding rate limit: a number from 0 to 100.
 *
 * @param message - Error when the value is not a valid rate limit.
 * @returns A validator for the rate-limit field.
 */
function rateLimitValidator(message: string): Validator<string> {
  return (value) => {
    const rate = Number(value.trim())
    return value.trim() !== '' &&
      Number.isFinite(rate) &&
      rate >= 0 &&
      rate <= MAX_GEOCODING_RATE_LIMIT
      ? null
      : message
  }
}

/**
 * Validates the tile URL template: non-empty and containing the `{z}/{x}/{y}`
 * placeholders. The backend enforces the full rule set (HTTPS, blocked
 * schemes) authoritatively; this is fast client feedback for the common case.
 *
 * @param requiredMessage - Error when the field is empty.
 * @param placeholderMessage - Error when a coordinate placeholder is missing.
 * @returns A validator for the tile URL field.
 */
function tileUrlValidator(requiredMessage: string, placeholderMessage: string): Validator<string> {
  return (value) => {
    const trimmed = value.trim()
    if (!trimmed) {
      return requiredMessage
    }
    return TILE_PLACEHOLDERS.every((placeholder) => trimmed.includes(placeholder))
      ? null
      : placeholderMessage
  }
}

/**
 * Owns the state of the server settings form: values, validation, saving, the
 * tile-server preset selection and the env-managed lookups. The tab components
 * read it through {@link useServerSettingsFormContext}.
 *
 * @param props - The loaded settings and tile presets (the parent mounts the form only after load).
 * @returns The form state and helpers.
 */
export function useServerSettingsForm(props: {
  settings: ServerSettings
  templates: TileMapsTemplate[]
}) {
  const { t } = useI18n()
  const toasts = useToasts()
  const updateMutation = useUpdateServerSettingsMutation()
  const handleIdpChallenge = useIdpReauthChallenge()

  const initialValues = toFormValues(props.settings)

  // A security-relevant change is confirmed with the administrator's own step-up, collected by a dialog.
  const isStepUpOpen = ref(false)
  const idpReauth = ref<IdpReauth | null>(null)
  const pendingResume = useSettingsStepUpResume()

  /**
   * The environment variable that sets a field, or undefined when it is editable.
   *
   * @param field - The backend field name (snake_case, as in `env_managed`).
   * @returns The variable name.
   */
  function envVar(field: string): string | undefined {
    return props.settings.envManaged[field]
  }

  /**
   * The hint under an env-managed field, naming the variable that sets it.
   *
   * @param field - The backend field name.
   * @returns The hint, or undefined when the field is editable.
   */
  function envHint(field: string): string | undefined {
    const name = envVar(field)
    return name ? t('settings.server.envLocked', { name }) : undefined
  }

  /**
   * The environment variables that set any of the given fields, without repeats.
   *
   * @param fields - Backend field names (snake_case, as in `env_managed`).
   * @returns The variable names, empty when every field is editable.
   */
  function envNames(fields: string[]): string[] {
    return [...new Set(fields.map(envVar).filter((name): name is string => Boolean(name)))]
  }

  /**
   * Finds the preset whose URL matches the given template, or the `custom`
   * sentinel when none does.
   *
   * @param url - The current tile URL template.
   * @returns The matching preset id, or `custom`.
   */
  function detectTemplate(url: string): string {
    return (
      props.templates.find((template) => template.urlTemplate === url)?.templateId ??
      CUSTOM_TEMPLATE
    )
  }

  /**
   * Whether the edits change a security-relevant setting, which needs the administrator's step-up.
   *
   * @param formValues - The form values.
   * @returns True when one of the settings the server lists in `stepUpFields` differs from the saved one.
   */
  function changesSecuritySetting(formValues: ServerSettingsFormValues): boolean {
    const normalized = (value: unknown): unknown =>
      typeof value === 'string' ? value.trim() : value
    return props.settings.stepUpFields.some(
      (field) =>
        field in formValues &&
        normalized(formValues[field as keyof ServerSettingsFormValues]) !==
          normalized(initialValues[field as keyof ServerSettingsFormValues]),
    )
  }

  /**
   * Saves the form, asking for the administrator's step-up first when a security-relevant setting changed.
   *
   * @param formValues - The validated form values.
   */
  async function submitForm(formValues: ServerSettingsFormValues): Promise<void> {
    if (changesSecuritySetting(formValues)) {
      isStepUpOpen.value = true
      return
    }
    await save(formValues, null)
  }

  /**
   * Saves the form with the step-up from the dialog.
   *
   * @param stepUp - The administrator's step-up from the dialog.
   */
  async function confirmStepUp(stepUp: StepUpInput): Promise<void> {
    await save({ ...values }, stepUp)
  }

  /**
   * Persists the whole settings record, merging the form edits over the freshest
   * server state so `id` and `loginPhotoSet` round-trip untouched. Outcomes are
   * surfaced as toasts; the error is not rethrown, so no inline submit error
   * banner appears. A refused step-up keeps the dialog open for another try.
   *
   * @param formValues - The validated form values.
   * @param stepUp - The administrator's step-up, or `null` when no security-relevant setting changed.
   */
  async function save(
    formValues: ServerSettingsFormValues,
    stepUp: StepUpInput | null,
  ): Promise<void> {
    const {
      tileserverApiKey,
      removeTileserverApiKey,
      geocodingApiKey,
      removeGeocodingApiKey,
      geocodingHost,
      geocodingRateLimit,
      sessionIdleTimeoutHours,
      sessionAbsoluteTimeoutHours,
      accessTokenExpireMinutes,
      refreshTokenExpireDays,
      apiKeyMaxLifetimeDays,
      readNotificationRetentionDays,
      auditRetentionDays,
      ...editable
    } = formValues
    // undefined keeps the stored key, null removes it, a string replaces it.
    const apiKey = removeTileserverApiKey ? null : tileserverApiKey.trim() || undefined
    const geocodingKey = removeGeocodingApiKey ? null : geocodingApiKey.trim() || undefined
    try {
      await updateMutation.mutateAsync({
        settings: {
          ...props.settings,
          ...editable,
          geocodingHost: geocodingHost.trim() || null,
          geocodingRateLimit: Number(geocodingRateLimit.trim()),
          sessionIdleTimeoutHours: Number(sessionIdleTimeoutHours.trim()),
          sessionAbsoluteTimeoutHours: Number(sessionAbsoluteTimeoutHours.trim()),
          accessTokenExpireMinutes: Number(accessTokenExpireMinutes.trim()),
          refreshTokenExpireDays: Number(refreshTokenExpireDays.trim()),
          apiKeyMaxLifetimeDays: Number(apiKeyMaxLifetimeDays.trim()),
          readNotificationRetentionDays: Number(readNotificationRetentionDays.trim()),
          auditRetentionDays: Number(auditRetentionDays.trim()),
          tileserverApiKey: apiKey,
          geocodingApiKey: geocodingKey,
        },
        stepUp,
      })
      isStepUpOpen.value = false
      toasts.success(t('settings.server.saveSuccess'))
    } catch (error) {
      if (handleIdpChallenge(error)) {
        return
      }
      if (isStepUpFailed(error)) {
        // Also when the form sent no step-up: the backend asked for one, so the dialog collects it.
        isStepUpOpen.value = true
        toasts.error(t('settings.security.linked.invalidCredentials'))
        return
      }
      isStepUpOpen.value = false
      // 412 is a refusal to overwrite: another admin saved since this form was loaded.
      toasts.error(
        error instanceof HttpError && error.status === 412
          ? t('settings.server.staleError')
          : t('settings.server.saveError'),
      )
    }
  }

  /**
   * The form values that survive the identity-provider sign-in. The API keys are left out, so they never
   * reach storage; `keysTyped` tells the resumed form that the administrator has to enter them again.
   *
   * @returns The draft entries and whether an API key was being set.
   */
  function draftValues(): Record<string, unknown> {
    const draft: Record<string, unknown> = { ...values }
    for (const field of SECRET_FIELDS) {
      delete draft[field]
    }
    return { ...draft, keysTyped: SECRET_FIELDS.some((field) => values[field] !== '') }
  }

  /**
   * Keeps the stored draft entries that have the type of the matching form field, except the API keys.
   *
   * @param raw - The draft stored when the sign-in started.
   * @returns The entries that can be applied to the form.
   */
  function pickDraft(raw: unknown): Partial<ServerSettingsFormValues> {
    const stored: Record<string, unknown> =
      typeof raw === 'object' && raw !== null ? { ...raw } : {}
    const picked: Record<string, unknown> = {}
    for (const [key, base] of Object.entries(initialValues)) {
      if (
        !(SECRET_FIELDS as readonly string[]).includes(key) &&
        typeof stored[key] === typeof base
      ) {
        picked[key] = stored[key]
      }
    }
    return picked as Partial<ServerSettingsFormValues>
  }

  /**
   * Restores the draft and the sign-in proof. An API key the administrator was setting is not stored, so then
   * the form waits for it to be entered again instead of saving without it.
   *
   * @param resume - The sign-in the page returned from.
   */
  function reopen(resume: IdpStepUpResume): void {
    pendingResume.value = null
    Object.assign(values, pickDraft(resume.pending.draft))
    idpReauth.value = resume.reauth
    const draft = resume.pending.draft
    const keysTyped =
      typeof draft === 'object' &&
      draft !== null &&
      'keysTyped' in draft &&
      draft.keysTyped === true
    isStepUpOpen.value = !keysTyped
  }

  /**
   * The out-of-range message for a numeric session setting.
   *
   * @param range - The inclusive bounds.
   * @returns The translated message.
   */
  function rangeMessage(range: { readonly min: number; readonly max: number }): string {
    return t('settings.server.session.invalidRange', range)
  }

  const form = useForm<ServerSettingsFormValues>({
    initialValues,
    validators: {
      tileserverUrl: tileUrlValidator(
        t('settings.server.maps.urlRequired'),
        t('settings.server.maps.urlInvalid'),
      ),
      geocodingRateLimit: rateLimitValidator(t('settings.server.geocoding.rateLimitInvalid')),
      sessionIdleTimeoutHours: integerRangeValidator(
        IDLE_HOURS_RANGE,
        rangeMessage(IDLE_HOURS_RANGE),
      ),
      sessionAbsoluteTimeoutHours: (value: string): string | null =>
        integerRangeValidator(ABSOLUTE_HOURS_RANGE, rangeMessage(ABSOLUTE_HOURS_RANGE))(value) ??
        (Number(value.trim()) < Number(form.values.sessionIdleTimeoutHours.trim())
          ? t('settings.server.session.absoluteBelowIdle')
          : null),
      accessTokenExpireMinutes: integerRangeValidator(
        ACCESS_MINUTES_RANGE,
        rangeMessage(ACCESS_MINUTES_RANGE),
      ),
      refreshTokenExpireDays: integerRangeValidator(
        REFRESH_DAYS_RANGE,
        rangeMessage(REFRESH_DAYS_RANGE),
      ),
      apiKeyMaxLifetimeDays: integerRangeValidator(
        API_KEY_DAYS_RANGE,
        rangeMessage(API_KEY_DAYS_RANGE),
      ),
      readNotificationRetentionDays: integerRangeValidator(
        RETENTION_DAYS_RANGE,
        rangeMessage(RETENTION_DAYS_RANGE),
      ),
      auditRetentionDays: (value: string): string | null =>
        value.trim() === '0'
          ? null
          : integerRangeValidator(
              AUDIT_RETENTION_DAYS_RANGE,
              t('settings.server.retention.auditTrailInvalid', AUDIT_RETENTION_DAYS_RANGE),
            )(value),
    },
    onSubmit: submitForm,
  })
  const { values } = form

  // The form and the step-up come back once the identity-provider sign-in returns for the server settings.
  useResumeOnce(
    () => pendingResume.value,
    'admin_server_settings_edit',
    () => true,
    (resume) => reopen(resume),
  )

  const isGeocodeService = computed(() => values.geocodingService === 'geocode')
  const geocodingHostPlaceholder = computed(
    () => GEOCODING_DEFAULT_HOSTS[values.geocodingService] ?? '',
  )

  const selectedTemplate = ref(detectTemplate(props.settings.tileserverUrl))
  const isCustomTemplate = computed(() => selectedTemplate.value === CUSTOM_TEMPLATE)
  const selectedTemplateData = computed(
    () =>
      props.templates.find((template) => template.templateId === selectedTemplate.value) ?? null,
  )

  /**
   * Selects a tile-server preset. Applying one fills the URL/attribution/background
   * and clears the API key (presets either embed it or need it configured
   * elsewhere); the three fields are then read-only until the user switches back
   * to "custom".
   *
   * @param templateId - The preset id, or the `custom` sentinel.
   */
  function selectTemplate(templateId: string): void {
    selectedTemplate.value = templateId
    const template = props.templates.find((entry) => entry.templateId === templateId)
    if (!template) {
      return
    }
    values.tileserverUrl = template.urlTemplate
    values.tileserverAttribution = template.attribution
    values.tileserverApiKey = ''
    values.removeTileserverApiKey = props.settings.tileserverApiKeySet
    values.mapBackgroundColor = template.mapBackgroundColor
  }

  /** The tabs holding at least one edited field. */
  const dirtyTabs = computed(() => {
    const tabs = new Set<SettingsTab>()
    for (const key of Object.keys(FIELD_TABS) as (keyof ServerSettingsFormValues)[]) {
      if (values[key] !== initialValues[key]) {
        tabs.add(FIELD_TABS[key])
      }
    }
    return tabs
  })

  /** Drops every edit and restores the saved values, preset selection included. */
  function discard(): void {
    form.reset()
    selectedTemplate.value = detectTemplate(props.settings.tileserverUrl)
  }

  return {
    ...form,
    settings: computed(() => props.settings),
    templates: computed(() => props.templates),
    envVar,
    envHint,
    envNames,
    isGeocodeService,
    geocodingHostPlaceholder,
    selectedTemplate,
    selectedTemplateData,
    isCustomTemplate,
    selectTemplate,
    dirtyTabs,
    discard,
    isStepUpOpen,
    idpReauth,
    draftValues,
    confirmStepUp,
    isUpdating: computed(() => updateMutation.isPending.value),
  }
}

/** The form state the tab components share. */
export type ServerSettingsFormContext = ReturnType<typeof useServerSettingsForm>

const SERVER_SETTINGS_FORM_KEY: InjectionKey<ServerSettingsFormContext> =
  Symbol('serverSettingsForm')

/**
 * Makes the form state available to the tab components beneath the caller.
 *
 * @param context - The form state from {@link useServerSettingsForm}.
 */
export function provideServerSettingsForm(context: ServerSettingsFormContext): void {
  provide(SERVER_SETTINGS_FORM_KEY, context)
}

/**
 * Reads the form state provided by the server settings form.
 *
 * @returns The shared form state.
 * @throws {Error} When called outside the server settings form.
 */
export function useServerSettingsFormContext(): ServerSettingsFormContext {
  const context = inject(SERVER_SETTINGS_FORM_KEY)
  if (!context) {
    throw new Error('useServerSettingsFormContext must be used inside the server settings form')
  }
  return context
}
