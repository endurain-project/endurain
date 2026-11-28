<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown } from '@lucide/vue'

import type { CorosStatus, DateRange } from '@/features/integrations/types'
import type { IdpReauth, StepUpInput } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import RetrieveRangeDialog from '@/features/integrations/components/RetrieveRangeDialog.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import StepUpDialog from '@/features/security/components/StepUpDialog.vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogos'
import { useToasts } from '@/composables/useToasts'
import { useAdminStepUp } from '@/features/security/composables/useAdminStepUp'
import {
  isStepUpFailed,
  isStepUpLocked,
  useIdpReauthChallenge,
} from '@/features/security/composables/useIdpStepUp'
import {
  useCorosStatusQuery,
  useRetrievalOutcome,
  useSyncCorosMutation,
  useUnlinkCorosMutation,
} from '@/features/integrations/composables/useIntegrations'
import { startCorosAuthorization } from '@/features/integrations/services/coros'
import { formatMediumDateTime } from '@/utils/datetime'

const props = defineProps<{
  /** Whether a COROS account is currently connected. */
  linked: boolean
  /** The identity-provider sign-in the browser just returned from, if any. */
  resume: IdpStepUpResume | null
}>()

const { t, te, locale } = useI18n()
const toasts = useToasts()
const retrieval = useRetrievalOutcome('COROS')

const statusQuery = useCorosStatusQuery(() => props.linked)
const syncMutation = useSyncCorosMutation()
const unlinkMutation = useUnlinkCorosMutation()

const isConnecting = ref(false)
const isActivitiesOpen = ref(false)
const isUnlinkOpen = ref(false)
const unlinkReauth = ref<IdpReauth | null>(null)
const handleIdpChallenge = useIdpReauthChallenge()
const { requirePassword, requireMfa } = useAdminStepUp()

/** Reopens the unlink dialog once the identity-provider sign-in returns. */
onMounted(() => {
  if (props.resume?.action === 'coros_unlink') {
    unlinkReauth.value = props.resume.reauth
    isUnlinkOpen.value = true
  }
})

const status = computed<CorosStatus | null>(() => statusQuery.data.value ?? null)

const lastSyncLabel = computed(() => {
  if (!status.value?.lastSyncAt) {
    return t('settings.integrations.coros.neverSynced')
  }
  return t('settings.integrations.coros.lastSync', {
    date: formatMediumDateTime(status.value.lastSyncAt, locale.value),
  })
})

const statusLabel = computed(() => {
  if (!status.value || status.value.lastSyncStatus === 'never') {
    return ''
  }
  if (status.value.lastSyncStatus === 'success') {
    return t('settings.integrations.coros.syncSuccess', {
      count: status.value.lastSyncActivityCount,
    })
  }
  const code = status.value.lastSyncError ?? 'processing_error'
  const key = `settings.integrations.coros.errors.${code}`
  return te(key) ? t(key) : t('settings.integrations.coros.errors.processing_error')
})

/** Sends the browser to COROS; the backend stores the state it will verify. */
async function connectCoros(): Promise<void> {
  isConnecting.value = true
  try {
    window.location.assign(await startCorosAuthorization())
  } catch {
    isConnecting.value = false
    toasts.error(t('settings.integrations.coros.connectError'))
  }
}

function syncNow(): void {
  syncMutation.mutate(undefined, {
    onSuccess: (job) => {
      toasts.info(t('settings.integrations.coros.syncQueued'))
      void retrieval.follow(job.id)
    },
    onError: (error) => {
      if (!retrieval.resumeOnConflict(error)) {
        toasts.error(t('settings.integrations.coros.syncError'))
      }
    },
  })
}

function onRetrieveActivities(range: DateRange): void {
  syncMutation.mutate(range, {
    onSuccess: (job) => {
      isActivitiesOpen.value = false
      toasts.info(t('settings.integrations.coros.syncQueued'))
      void retrieval.follow(job.id)
    },
    onError: (error) => {
      if (!retrieval.resumeOnConflict(error)) {
        toasts.error(t('settings.integrations.coros.syncError'))
      }
    },
  })
}

function confirmUnlink(stepUp: StepUpInput): void {
  unlinkMutation.mutate(stepUp, {
    onSuccess: () => {
      isUnlinkOpen.value = false
      toasts.success(t('settings.integrations.coros.unlinkSuccess'))
    },
    onError: (error) => {
      if (handleIdpChallenge(error)) {
        return
      }
      if (isStepUpLocked(error)) {
        toasts.error(t('settings.security.stepUp.tooManyAttempts'))
      } else if (isStepUpFailed(error)) {
        toasts.error(t('settings.security.linked.invalidCredentials'))
      } else {
        toasts.error(t('settings.integrations.coros.unlinkError'))
      }
    },
  })
}
</script>

<template>
  <Card class="flex flex-wrap items-center justify-between gap-3">
    <div class="flex min-w-0 items-center gap-3">
      <img
        :src="INTEGRATION_LOGOS.coros"
        :alt="t('settings.integrations.coros.title')"
        class="size-10 shrink-0 rounded object-contain"
      />
      <div class="min-w-0">
        <div class="flex items-center gap-2">
          <h2 class="text-card-heading">{{ t('settings.integrations.coros.title') }}</h2>
          <Badge v-if="props.linked" variant="secondary">
            {{ t('settings.integrations.connected') }}
          </Badge>
        </div>
        <p class="text-hint">{{ t('settings.integrations.coros.subtitle') }}</p>
        <p v-if="props.linked" class="text-hint">
          {{ lastSyncLabel }}
          <template v-if="statusLabel"> · {{ statusLabel }}</template>
        </p>
      </div>
    </div>

    <Button v-if="!props.linked" size="sm" :disabled="isConnecting" @click="connectCoros">
      {{ t('settings.integrations.connect') }}
    </Button>

    <DropdownMenu v-else>
      <DropdownMenuTrigger as-child>
        <Button variant="outline" size="sm">
          {{ t('settings.integrations.options') }}
          <ChevronDown class="size-4" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" class="w-56">
        <DropdownMenuItem :disabled="syncMutation.isPending.value" @select="syncNow">
          {{ t('settings.integrations.coros.syncNow') }}
        </DropdownMenuItem>
        <DropdownMenuItem @select="isActivitiesOpen = true">
          {{ t('settings.integrations.retrieveActivities') }}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem :disabled="isConnecting" @select="connectCoros">
          {{ t('settings.integrations.coros.reconnect') }}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          class="text-destructive hover:bg-destructive/10 hover:text-destructive focus:bg-destructive/10 focus:text-destructive data-[highlighted]:bg-destructive/10 data-[highlighted]:text-destructive"
          @select="isUnlinkOpen = true"
        >
          {{ t('settings.integrations.unlink') }}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>

    <RetrieveRangeDialog
      v-model:open="isActivitiesOpen"
      :title="t('settings.integrations.coros.retrieveActivitiesTitle')"
      :pending="syncMutation.isPending.value"
      @submit="onRetrieveActivities"
    />

    <StepUpDialog
      v-model:open="isUnlinkOpen"
      v-model:reauth="unlinkReauth"
      action="coros_unlink"
      :title="t('settings.integrations.coros.unlinkTitle')"
      :description="t('settings.integrations.coros.unlinkBody')"
      :confirm-label="t('settings.integrations.unlink')"
      :require-password="requirePassword"
      :require-mfa="requireMfa"
      destructive
      :pending="unlinkMutation.isPending.value"
      @confirm="confirmUnlink"
    />
  </Card>
</template>
