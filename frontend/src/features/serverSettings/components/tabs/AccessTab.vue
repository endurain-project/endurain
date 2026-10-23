<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { Alert } from '@/components/ui/alert'
import { Card } from '@/components/ui/card'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import EnvManagedHint from '@/features/serverSettings/components/EnvManagedHint.vue'
import EnvManagedNotice from '@/features/serverSettings/components/EnvManagedNotice.vue'
import { useServerSettingsFormContext } from '@/features/serverSettings/composables/useServerSettingsForm'

const { t } = useI18n()
const { values, errors, isSubmitting, handleSubmit, handleBlur, envVar, envHint, envNames } =
  useServerSettingsFormContext()

/** Minimum-length options for regular users: 8–20 (mirrors v1). */
const PASSWORD_REGULAR_LENGTHS = Array.from({ length: 13 }, (_, index) => index + 8)
/** Minimum-length options for admin users: 8–25 (mirrors v1). */
const PASSWORD_ADMIN_LENGTHS = Array.from({ length: 18 }, (_, index) => index + 8)
/** The session-policy fields an environment variable can lock. */
const SESSION_ENV_FIELDS = [
  'session_idle_timeout_enabled',
  'session_idle_timeout_hours',
  'session_absolute_timeout_hours',
  'access_token_expire_minutes',
  'refresh_token_expire_days',
]
</script>

<template>
  <form class="flex flex-col gap-3" novalidate @submit.prevent="handleSubmit">
    <Card class="flex flex-col gap-3" data-setting="section-sso">
      <h2 class="text-card-heading">{{ t('settings.server.sso.title') }}</h2>
      <Switch v-model="values.ssoEnabled" data-setting="sso-enabled" :disabled="isSubmitting">
        {{ t('settings.server.sso.enabled') }}
      </Switch>
      <Alert kind="info">{{ t('settings.server.sso.enabledInfo') }}</Alert>
      <Switch
        v-model="values.localLoginEnabled"
        data-setting="sso-local-login"
        :disabled="isSubmitting"
      >
        {{ t('settings.server.sso.localLogin') }}
      </Switch>
      <Alert v-if="!values.localLoginEnabled" kind="warning">
        {{ t('settings.server.sso.localLoginWarning') }}
      </Alert>
      <Switch
        v-model="values.ssoAutoRedirect"
        data-setting="sso-auto-redirect"
        :disabled="isSubmitting"
      >
        {{ t('settings.server.sso.autoRedirect') }}
      </Switch>
      <Alert kind="info">{{ t('settings.server.sso.autoRedirectInfo') }}</Alert>
    </Card>

    <Card class="flex flex-col gap-3" data-setting="section-signup">
      <h2 class="text-card-heading">{{ t('settings.server.signup.title') }}</h2>
      <Switch v-model="values.signupEnabled" data-setting="signup-enabled" :disabled="isSubmitting">
        {{ t('settings.server.signup.enabled') }}
      </Switch>
      <Switch
        v-model="values.signupRequireAdminApproval"
        data-setting="signup-admin-approval"
        :disabled="isSubmitting"
      >
        {{ t('settings.server.signup.adminApproval') }}
      </Switch>
      <Switch
        v-model="values.signupRequireEmailVerification"
        data-setting="signup-email-verification"
        :disabled="isSubmitting"
      >
        {{ t('settings.server.signup.emailVerification') }}
      </Switch>
    </Card>

    <Card class="flex flex-col gap-3" data-setting="section-password">
      <h2 class="text-card-heading">{{ t('settings.server.password.title') }}</h2>
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <FormField data-setting="password-type" :label="t('settings.server.password.type')">
          <template #default="{ fieldId }">
            <Select :id="fieldId" v-model="values.passwordType" :disabled="isSubmitting">
              <option value="strict">{{ t('settings.server.password.typeStrict') }}</option>
              <option value="length_only">
                {{ t('settings.server.password.typeLengthOnly') }}
              </option>
            </Select>
          </template>
        </FormField>

        <FormField
          data-setting="password-length-regular"
          :label="t('settings.server.password.lengthRegular')"
        >
          <template #default="{ fieldId }">
            <Select
              :id="fieldId"
              v-model="values.passwordLengthRegularUsers"
              :disabled="isSubmitting"
            >
              <option v-for="length in PASSWORD_REGULAR_LENGTHS" :key="length" :value="length">
                {{ length }}
              </option>
            </Select>
          </template>
        </FormField>

        <FormField
          data-setting="password-length-admin"
          :label="t('settings.server.password.lengthAdmin')"
        >
          <template #default="{ fieldId }">
            <Select
              :id="fieldId"
              v-model="values.passwordLengthAdminUsers"
              :disabled="isSubmitting"
            >
              <option v-for="length in PASSWORD_ADMIN_LENGTHS" :key="length" :value="length">
                {{ length }}
              </option>
            </Select>
          </template>
        </FormField>
      </div>
    </Card>

    <Card class="flex flex-col gap-3" data-setting="section-session">
      <div class="flex flex-col gap-1">
        <h2 class="text-card-heading">{{ t('settings.server.session.title') }}</h2>
        <p class="text-body">{{ t('settings.server.session.description') }}</p>
      </div>
      <EnvManagedNotice :names="envNames(SESSION_ENV_FIELDS)" />

      <Switch
        v-model="values.sessionIdleTimeoutEnabled"
        data-setting="session-timeouts-enabled"
        :disabled="isSubmitting || Boolean(envVar('session_idle_timeout_enabled'))"
      >
        {{ t('settings.server.session.timeoutsEnabled') }}
      </Switch>
      <EnvManagedHint :name="envVar('session_idle_timeout_enabled')" />

      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <FormField
          data-setting="session-idle-hours"
          :label="t('settings.server.session.idleHours')"
          :hint="
            envHint('session_idle_timeout_hours') ?? t('settings.server.session.idleHoursHint')
          "
          :error="errors.sessionIdleTimeoutHours"
        >
          <template #default="{ fieldId, describedBy, invalid }">
            <Input
              :id="fieldId"
              v-model="values.sessionIdleTimeoutHours"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              type="text"
              inputmode="numeric"
              maxlength="4"
              :disabled="
                isSubmitting ||
                !values.sessionIdleTimeoutEnabled ||
                Boolean(envVar('session_idle_timeout_hours'))
              "
              @blur="handleBlur('sessionIdleTimeoutHours')"
            />
          </template>
        </FormField>

        <FormField
          data-setting="session-absolute-hours"
          :label="t('settings.server.session.absoluteHours')"
          :hint="
            envHint('session_absolute_timeout_hours') ??
            t('settings.server.session.absoluteHoursHint')
          "
          :error="errors.sessionAbsoluteTimeoutHours"
        >
          <template #default="{ fieldId, describedBy, invalid }">
            <Input
              :id="fieldId"
              v-model="values.sessionAbsoluteTimeoutHours"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              type="text"
              inputmode="numeric"
              maxlength="4"
              :disabled="
                isSubmitting ||
                !values.sessionIdleTimeoutEnabled ||
                Boolean(envVar('session_absolute_timeout_hours'))
              "
              @blur="handleBlur('sessionAbsoluteTimeoutHours')"
            />
          </template>
        </FormField>

        <FormField
          data-setting="session-access-minutes"
          :label="t('settings.server.session.accessMinutes')"
          :hint="envHint('access_token_expire_minutes')"
          :error="errors.accessTokenExpireMinutes"
        >
          <template #default="{ fieldId, describedBy, invalid }">
            <Input
              :id="fieldId"
              v-model="values.accessTokenExpireMinutes"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              type="text"
              inputmode="numeric"
              maxlength="4"
              :disabled="isSubmitting || Boolean(envVar('access_token_expire_minutes'))"
              @blur="handleBlur('accessTokenExpireMinutes')"
            />
          </template>
        </FormField>

        <FormField
          data-setting="session-refresh-days"
          :label="t('settings.server.session.refreshDays')"
          :hint="envHint('refresh_token_expire_days')"
          :error="errors.refreshTokenExpireDays"
        >
          <template #default="{ fieldId, describedBy, invalid }">
            <Input
              :id="fieldId"
              v-model="values.refreshTokenExpireDays"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              type="text"
              inputmode="numeric"
              maxlength="3"
              :disabled="isSubmitting || Boolean(envVar('refresh_token_expire_days'))"
              @blur="handleBlur('refreshTokenExpireDays')"
            />
          </template>
        </FormField>
      </div>
    </Card>

    <Card class="flex flex-col gap-3" data-setting="section-sharing">
      <h2 class="text-card-heading">{{ t('settings.server.sharing.title') }}</h2>
      <Switch
        v-model="values.publicShareableLinks"
        data-setting="sharing-enabled"
        :disabled="isSubmitting"
      >
        {{ t('settings.server.sharing.enabled') }}
      </Switch>
      <Alert v-if="values.publicShareableLinks" kind="warning">
        {{ t('settings.server.sharing.enabledWarning') }}
      </Alert>
      <Switch
        v-model="values.publicShareableLinksUserInfo"
        data-setting="sharing-user-info"
        :disabled="isSubmitting || !values.publicShareableLinks"
      >
        {{ t('settings.server.sharing.userInfo') }}
      </Switch>
      <Alert
        v-if="values.publicShareableLinks && values.publicShareableLinksUserInfo"
        kind="warning"
      >
        {{ t('settings.server.sharing.userInfoWarning') }}
      </Alert>
    </Card>
  </form>
</template>
