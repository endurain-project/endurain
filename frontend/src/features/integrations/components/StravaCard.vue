<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'
import { ChevronDown } from '@lucide/vue'

import type { DateRange, StravaClientInput } from '@/features/integrations/types'
import type { IdpReauth, StepUpInput } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import RetrieveRangeDialog from '@/features/integrations/components/RetrieveRangeDialog.vue'
import StravaConnectDialog from '@/features/integrations/components/StravaConnectDialog.vue'
import { Alert } from '@/components/ui/alert'
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
import { useAdminStepUp } from '@/features/security/composables/useAdminStepUp'
import {
  isStepUpFailed,
  isStepUpLocked,
  useIdpReauthChallenge,
} from '@/features/security/composables/useIdpStepUp'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogos'
import { useToasts } from '@/composables/useToasts'
import { isStaleWrite } from '@/services/ifMatch'
import { formatMediumDate } from '@/utils/datetime'
import { queryKeys } from '@/services/queryKeys'
import {
  useRetrievalOutcome,
  useRetrieveStravaActivitiesMutation,
  useRetrieveStravaGearMutation,
  useUnlinkStravaMutation,
} from '@/features/integrations/composables/useIntegrations'
import {
  buildStravaAuthUrl,
  setStravaClient,
  beginStravaState,
} from '@/features/integrations/services/strava'

const props = defineProps<{
  /** Whether a Strava account is currently connected. */
  linked: boolean
  /** When Strava access was revoked on Strava, or `null` while access is intact. */
  revokedAt: string | null
  /** When Strava-synced activities and gear are deleted unless Strava is reconnected, or `null`. */
  dataDeletionAt: string | null
  /** The integrations row version the profile was read at, sent as `If-Match` with the client. */
  integrationsVersion: number
  /** The identity-provider sign-in the browser just returned from, if any. */
  resume: IdpStepUpResume | null
}>()

const { t, locale } = useI18n()
const toasts = useToasts()
const queryClient = useQueryClient()
const retrieval = useRetrievalOutcome('Strava')

const activitiesMutation = useRetrieveStravaActivitiesMutation()
const gearMutation = useRetrieveStravaGearMutation()
const unlinkMutation = useUnlinkStravaMutation()

const handleIdpChallenge = useIdpReauthChallenge()
const { requirePassword, requireMfa } = useAdminStepUp()

const isConnectOpen = ref(false)
const isActivitiesOpen = ref(false)
const isUnlinkOpen = ref(false)
const connectReauth = ref<IdpReauth | null>(null)
const unlinkReauth = ref<IdpReauth | null>(null)

/** Reopens the dialog the identity-provider sign-in was for, with its proof. */
onMounted(() => {
  if (props.resume?.action === 'strava_client_set') {
    connectReauth.value = props.resume.reauth
    isConnectOpen.value = true
  } else if (props.resume?.action === 'strava_unlink') {
    unlinkReauth.value = props.resume.reauth
    isUnlinkOpen.value = true
  }
})

/** Reports a refused step-up, or returns `false` when the error is something else. */
function reportStepUpError(error: unknown): boolean {
  if (handleIdpChallenge(error)) {
    return true
  }
  if (isStepUpLocked(error)) {
    toasts.error(t('settings.security.stepUp.tooManyAttempts'))
    return true
  }
  if (isStepUpFailed(error)) {
    toasts.error(t('settings.security.linked.invalidCredentials'))
    return true
  }
  return false
}
// Held true through the full-page redirect so the dialog button stays busy.
const isConnecting = ref(false)

/**
 * Obtains the state, stores the client credentials, then sends the browser to Strava's
 * OAuth page. Strava redirects back to `/strava/callback` to finish linking.
 */
async function connectStrava(input: StravaClientInput, stepUp: StepUpInput): Promise<void> {
  isConnecting.value = true
  try {
    const state = await beginStravaState()
    await setStravaClient(input, stepUp, props.integrationsVersion)
    window.location.assign(buildStravaAuthUrl(state, input.clientId))
  } catch (error) {
    isConnecting.value = false
    if (isStaleWrite(error)) {
      // The integrations row changed since the profile was read; reload it and close the dialog so
      // the retry starts from the current version.
      void queryClient.invalidateQueries({ queryKey: queryKeys.profile.all() })
      isConnectOpen.value = false
      toasts.error(t('app.staleError'))
    } else if (!reportStepUpError(error)) {
      toasts.error(t('settings.integrations.strava.connectError'))
    }
  }
}

function onRetrieveActivities(range: DateRange): void {
  activitiesMutation.mutate(range, {
    onSuccess: (job) => {
      isActivitiesOpen.value = false
      toasts.info(t('settings.integrations.strava.retrievingActivities'))
      void retrieval.follow(job.id)
    },
    onError: () => toasts.error(t('settings.integrations.strava.retrieveActivitiesError')),
  })
}

function retrieveGear(): void {
  gearMutation.mutate(undefined, {
    onSuccess: (job) => {
      toasts.info(t('settings.integrations.strava.retrievingGear'))
      void retrieval.follow(job.id)
    },
    onError: (error) => {
      if (!retrieval.resumeOnConflict(error)) {
        toasts.error(t('settings.integrations.strava.retrieveGearError'))
      }
    },
  })
}

function confirmUnlink(stepUp: StepUpInput): void {
  unlinkMutation.mutate(stepUp, {
    onSuccess: () => {
      isUnlinkOpen.value = false
      toasts.success(t('settings.integrations.strava.unlinkSuccess'))
    },
    onError: (error) => {
      if (!reportStepUpError(error)) {
        toasts.error(t('settings.integrations.strava.unlinkError'))
      }
    },
  })
}
</script>

<template>
  <Card class="flex flex-wrap items-center justify-between gap-3">
    <div class="flex min-w-0 items-center gap-3">
      <img
        :src="INTEGRATION_LOGOS.stravaMark"
        :alt="t('settings.integrations.strava.title')"
        class="size-10 shrink-0 object-contain rounded"
      />
      <div class="min-w-0">
        <div class="flex items-center gap-2">
          <h2 class="text-card-heading">{{ t('settings.integrations.strava.title') }}</h2>
          <Badge v-if="props.linked" variant="secondary">
            {{ t('settings.integrations.connected') }}
          </Badge>
        </div>
        <p class="text-hint">{{ t('settings.integrations.strava.subtitle') }}</p>
      </div>
    </div>

    <Button v-if="!props.linked" size="sm" @click="isConnectOpen = true">
      {{ props.revokedAt ? t('settings.integrations.relink') : t('settings.integrations.connect') }}
    </Button>

    <DropdownMenu v-else>
      <DropdownMenuTrigger as-child>
        <Button variant="outline" size="sm">
          {{ t('settings.integrations.options') }}
          <ChevronDown class="size-4" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" class="w-56">
        <DropdownMenuItem @select="isActivitiesOpen = true">
          {{ t('settings.integrations.retrieveActivities') }}
        </DropdownMenuItem>
        <DropdownMenuItem @select="retrieveGear">
          {{ t('settings.integrations.retrieveGear') }}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem @select="isConnectOpen = true">
          {{ t('settings.integrations.relink') }}
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

    <Alert
      v-if="!props.linked && props.revokedAt && props.dataDeletionAt"
      kind="warning"
      class="w-full"
    >
      {{
        t('settings.integrations.strava.revokedNotice', {
          revokedAt: formatMediumDate(props.revokedAt, locale),
          deletionAt: formatMediumDate(props.dataDeletionAt, locale),
        })
      }}
    </Alert>

    <StravaConnectDialog
      v-model:open="isConnectOpen"
      v-model:reauth="connectReauth"
      :pending="isConnecting"
      :require-password="requirePassword"
      :require-mfa="requireMfa"
      :restored-context="
        props.resume?.action === 'strava_client_set' ? props.resume.pending : undefined
      "
      @submit="connectStrava"
    />

    <RetrieveRangeDialog
      v-model:open="isActivitiesOpen"
      :title="t('settings.integrations.strava.retrieveActivitiesTitle')"
      :pending="activitiesMutation.isPending.value"
      @submit="onRetrieveActivities"
    />

    <StepUpDialog
      v-model:open="isUnlinkOpen"
      v-model:reauth="unlinkReauth"
      action="strava_unlink"
      :title="t('settings.integrations.strava.unlinkTitle')"
      :description="t('settings.integrations.strava.unlinkBody')"
      :confirm-label="t('settings.integrations.unlink')"
      :require-password="requirePassword"
      :require-mfa="requireMfa"
      destructive
      :pending="unlinkMutation.isPending.value"
      @confirm="confirmUnlink"
    />
  </Card>
</template>
