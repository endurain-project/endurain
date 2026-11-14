<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown } from '@lucide/vue'

import type { DateRange } from '@/features/integrations/types'
import type { IdpReauth, StepUpInput } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import GarminLoginDialog from '@/features/integrations/components/GarminLoginDialog.vue'
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
import { useAdminStepUp } from '@/features/security/composables/useAdminStepUp'
import {
  isStepUpFailed,
  isStepUpLocked,
  useIdpReauthChallenge,
} from '@/features/security/composables/useIdpStepUp'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogos'
import { useToasts } from '@/composables/useToasts'
import {
  useRetrieveGarminActivitiesMutation,
  useRetrieveGarminGearMutation,
  useRetrievalOutcome,
  useRetrieveGarminHealthMutation,
  useUnlinkGarminMutation,
} from '@/features/integrations/composables/useIntegrations'

const props = defineProps<{
  /** Whether a Garmin Connect account is currently connected. */
  linked: boolean
  /** The identity-provider sign-in the browser just returned from, if any. */
  resume: IdpStepUpResume | null
}>()

const { t } = useI18n()
const toasts = useToasts()
const retrieval = useRetrievalOutcome('Garmin Connect')

const activitiesMutation = useRetrieveGarminActivitiesMutation()
const gearMutation = useRetrieveGarminGearMutation()
const healthMutation = useRetrieveGarminHealthMutation()
const unlinkMutation = useUnlinkGarminMutation()

const isConnectOpen = ref(false)
const isActivitiesOpen = ref(false)
const isHealthOpen = ref(false)
const isUnlinkOpen = ref(false)
const unlinkReauth = ref<IdpReauth | null>(null)
const handleIdpChallenge = useIdpReauthChallenge()
const { requirePassword, requireMfa } = useAdminStepUp()

/** Reopens the unlink dialog once the identity-provider sign-in returns. */
onMounted(() => {
  if (props.resume?.action === 'garmin_unlink') {
    unlinkReauth.value = props.resume.reauth
    isUnlinkOpen.value = true
  }
})

function onRetrieveActivities(range: DateRange): void {
  activitiesMutation.mutate(range, {
    onSuccess: (job) => {
      isActivitiesOpen.value = false
      toasts.info(t('settings.integrations.garmin.retrievingActivities'))
      void retrieval.follow(job.id)
    },
    onError: () => toasts.error(t('settings.integrations.garmin.retrieveActivitiesError')),
  })
}

function onRetrieveHealth(range: DateRange): void {
  healthMutation.mutate(range, {
    onSuccess: (job) => {
      isHealthOpen.value = false
      toasts.info(t('settings.integrations.garmin.retrievingHealth'))
      void retrieval.follow(job.id)
    },
    onError: (error) => {
      if (!retrieval.resumeOnConflict(error)) {
        toasts.error(t('settings.integrations.garmin.retrieveHealthError'))
      }
    },
  })
}

function retrieveGear(): void {
  gearMutation.mutate(undefined, {
    onSuccess: (job) => {
      toasts.info(t('settings.integrations.garmin.retrievingGear'))
      void retrieval.follow(job.id)
    },
    onError: (error) => {
      if (!retrieval.resumeOnConflict(error)) {
        toasts.error(t('settings.integrations.garmin.retrieveGearError'))
      }
    },
  })
}

function confirmUnlink(stepUp: StepUpInput): void {
  unlinkMutation.mutate(stepUp, {
    onSuccess: () => {
      isUnlinkOpen.value = false
      toasts.success(t('settings.integrations.garmin.unlinkSuccess'))
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
        toasts.error(t('settings.integrations.garmin.unlinkError'))
      }
    },
  })
}
</script>

<template>
  <Card class="flex flex-wrap items-center justify-between gap-3">
    <div class="flex min-w-0 items-center gap-3">
      <img
        :src="INTEGRATION_LOGOS.garminApp"
        :alt="t('settings.integrations.garmin.title')"
        class="size-10 shrink-0 rounded object-contain"
      />
      <div class="min-w-0">
        <div class="flex items-center gap-2">
          <h2 class="text-card-heading">{{ t('settings.integrations.garmin.title') }}</h2>
          <Badge v-if="props.linked" variant="secondary">
            {{ t('settings.integrations.connected') }}
          </Badge>
        </div>
        <p class="text-hint">{{ t('settings.integrations.garmin.subtitle') }}</p>
      </div>
    </div>

    <Button v-if="!props.linked" size="sm" @click="isConnectOpen = true">
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
        <DropdownMenuItem @select="isActivitiesOpen = true">
          {{ t('settings.integrations.retrieveActivities') }}
        </DropdownMenuItem>
        <DropdownMenuItem @select="retrieveGear">
          {{ t('settings.integrations.retrieveGear') }}
        </DropdownMenuItem>
        <DropdownMenuItem @select="isHealthOpen = true">
          {{ t('settings.integrations.garmin.retrieveHealth') }}
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

    <GarminLoginDialog v-model:open="isConnectOpen" />

    <RetrieveRangeDialog
      v-model:open="isActivitiesOpen"
      :title="t('settings.integrations.garmin.retrieveActivitiesTitle')"
      :pending="activitiesMutation.isPending.value"
      @submit="onRetrieveActivities"
    />

    <RetrieveRangeDialog
      v-model:open="isHealthOpen"
      :title="t('settings.integrations.garmin.retrieveHealthTitle')"
      :pending="healthMutation.isPending.value"
      @submit="onRetrieveHealth"
    />

    <StepUpDialog
      v-model:open="isUnlinkOpen"
      v-model:reauth="unlinkReauth"
      action="garmin_unlink"
      :title="t('settings.integrations.garmin.unlinkTitle')"
      :description="t('settings.integrations.garmin.unlinkBody')"
      :confirm-label="t('settings.integrations.unlink')"
      :require-password="requirePassword"
      :require-mfa="requireMfa"
      destructive
      :pending="unlinkMutation.isPending.value"
      @confirm="confirmUnlink"
    />
  </Card>
</template>
