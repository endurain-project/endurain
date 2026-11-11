<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Monitor, Trash2 } from '@lucide/vue'

import type { IdpReauth, KnownDevice, StepUpInput } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import StepUpDialog from '@/features/security/components/StepUpDialog.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useToasts } from '@/composables/useToasts'
import { HttpError } from '@/services/http'
import { formatMediumDateTime } from '@/utils/datetime'
import {
  isStepUpFailed,
  isStepUpLocked,
  useIdpReauthChallenge,
} from '@/features/security/composables/useIdpStepUp'
import {
  useForgetKnownDeviceMutation,
  useKnownDevicesQuery,
} from '@/features/security/composables/useSecurity'

const props = defineProps<{
  /** Whether the account has a local password (gates the step-up password field). */
  hasLocalPassword: boolean
  /** Whether MFA is enabled (gates the step-up MFA-code field). */
  mfaEnabled: boolean
  /** The identity-provider sign-in the browser just returned from, if any. */
  resume: IdpStepUpResume | null
}>()

/**
 * The Known devices card: the devices the account is known to sign in from, with the
 * current one badged. Forgetting a device needs step-up, signs the device out (this browser
 * included, when it is the current device) and makes the next sign-in from it count as a new
 * device.
 */
const { t, locale } = useI18n()
const toasts = useToasts()
const handleIdpChallenge = useIdpReauthChallenge()

const { data, isPending, isError, refetch } = useKnownDevicesQuery()
const devices = computed(() => data.value ?? [])
const forgetMutation = useForgetKnownDeviceMutation()

const isStepUpOpen = ref(false)
const idpReauth = ref<IdpReauth | null>(null)
const deviceIdToForget = ref<number | null>(null)
const forgetDescription = computed(() =>
  devices.value.some((device) => device.id === deviceIdToForget.value && device.current)
    ? t('settings.security.devices.forgetCurrentDescription')
    : t('settings.security.devices.forgetDescription'),
)

/** A device label built from browser + OS, falling back to the device type. */
function deviceLabel(device: KnownDevice): string {
  return (
    [device.browser, device.operatingSystem].filter(Boolean).join(' · ') ||
    device.deviceType ||
    t('settings.security.devices.unknown')
  )
}

function openForget(device: KnownDevice): void {
  deviceIdToForget.value = device.id
  idpReauth.value = null
  isStepUpOpen.value = true
}

/** Reopens the dialog for the pending device once the identity-provider sign-in returns. */
onMounted(() => {
  const { resume } = props
  const id = resume?.pending.deviceId
  if (resume?.action === 'profile_device_forget' && typeof id === 'number') {
    deviceIdToForget.value = id
    idpReauth.value = resume.reauth
    isStepUpOpen.value = true
  }
})

/** Forgets the pending device after step-up. */
function onConfirm(input: StepUpInput): void {
  const deviceId = deviceIdToForget.value
  if (deviceId === null) {
    return
  }
  forgetMutation.mutate(
    { deviceId, input },
    {
      onSuccess: () => {
        isStepUpOpen.value = false
        idpReauth.value = null
        toasts.success(t('settings.security.devices.forgetSuccess'))
      },
      onError: (error) => {
        if (handleIdpChallenge(error)) {
          return
        }
        if (isStepUpLocked(error)) {
          toasts.error(t('settings.security.stepUp.tooManyAttempts'))
        } else if (isStepUpFailed(error)) {
          toasts.error(t('settings.security.linked.invalidCredentials'))
        } else if (error instanceof HttpError && error.status === 404) {
          isStepUpOpen.value = false
          toasts.error(t('settings.security.devices.forgetNotFound'))
        } else {
          toasts.error(t('settings.security.devices.forgetError'))
        }
      },
    },
  )
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-col gap-1">
      <h2 class="text-card-heading">{{ t('settings.security.devices.title') }}</h2>
      <p class="text-hint">{{ t('settings.security.devices.subtitle') }}</p>
    </div>

    <!-- Loading -->
    <div v-if="isPending" class="flex flex-col gap-2" aria-busy="true">
      <Skeleton v-for="n in 2" :key="n" class="h-14 w-full rounded-input" />
    </div>

    <!-- Error -->
    <div v-else-if="isError" class="flex flex-col items-start gap-2">
      <p class="text-hint">{{ t('settings.security.devices.error') }}</p>
      <Button variant="outline" size="sm" @click="() => refetch()">
        {{ t('settings.security.retry') }}
      </Button>
    </div>

    <!-- Empty -->
    <p v-else-if="devices.length === 0" class="text-hint">
      {{ t('settings.security.devices.empty') }}
    </p>

    <!-- List -->
    <ul v-else class="divide-y divide-border overflow-hidden rounded-card border border-border">
      <li
        v-for="device in devices"
        :key="device.id"
        class="flex items-center justify-between gap-3 px-4 py-3"
      >
        <div class="flex min-w-0 items-center gap-3">
          <Monitor class="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div class="min-w-0">
            <div class="flex min-w-0 items-center gap-2">
              <p class="text-body">{{ deviceLabel(device) }}</p>
              <Badge v-if="device.current" variant="secondary" class="shrink-0">
                {{ t('settings.security.devices.current') }}
              </Badge>
            </div>
            <p class="text-hint">
              {{
                t('settings.security.devices.lastSeen', {
                  date: formatMediumDateTime(device.lastSeenAt, locale),
                })
              }}
            </p>
          </div>
        </div>
        <Button
          variant="ghostDestructive"
          size="icon-sm"
          :aria-label="t('settings.security.devices.forget')"
          @click="openForget(device)"
        >
          <Trash2 class="size-4" aria-hidden="true" />
        </Button>
      </li>
    </ul>

    <StepUpDialog
      v-model:open="isStepUpOpen"
      v-model:reauth="idpReauth"
      action="profile_device_forget"
      :pending-context="deviceIdToForget === null ? {} : { deviceId: deviceIdToForget }"
      :title="t('settings.security.devices.forgetTitle')"
      :description="forgetDescription"
      :confirm-label="t('settings.security.devices.forgetConfirm')"
      :require-password="props.hasLocalPassword"
      :require-mfa="props.mfaEnabled"
      destructive
      :pending="forgetMutation.isPending.value"
      @confirm="onConfirm"
    />
  </Card>
</template>
