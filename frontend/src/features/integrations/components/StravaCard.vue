<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown } from '@lucide/vue'

import type { DateRange, StravaClientInput } from '@/features/integrations/types'

import RetrieveRangeDialog from '@/features/integrations/components/RetrieveRangeDialog.vue'
import StravaConnectDialog from '@/features/integrations/components/StravaConnectDialog.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogos'
import { useToasts } from '@/composables/useToasts'
import {
  useRetrieveStravaActivitiesMutation,
  useRetrieveStravaGearMutation,
  useUnlinkStravaMutation,
} from '@/features/integrations/composables/useIntegrations'
import {
  buildStravaAuthUrl,
  setStravaClient,
  beginStravaState,
  clearStravaState,
} from '@/features/integrations/services/strava'

const props = defineProps<{
  /** Whether a Strava account is currently connected. */
  linked: boolean
  /** The integrations row version the profile was read at, sent as `If-Match` with the client. */
  integrationsVersion: number
}>()

const { t } = useI18n()
const toasts = useToasts()

const activitiesMutation = useRetrieveStravaActivitiesMutation()
const gearMutation = useRetrieveStravaGearMutation()
const unlinkMutation = useUnlinkStravaMutation()

const isConnectOpen = ref(false)
const isActivitiesOpen = ref(false)
const isUnlinkOpen = ref(false)
// Held true through the full-page redirect so the dialog button stays busy.
const isConnecting = ref(false)

/**
 * Obtains the state, stores the client credentials, then sends the browser to Strava's
 * OAuth page. Strava redirects back to `/strava/callback` to finish linking.
 */
async function connectStrava(input: StravaClientInput): Promise<void> {
  isConnecting.value = true
  try {
    const state = await beginStravaState()
    await setStravaClient(input, props.integrationsVersion)
    window.location.assign(buildStravaAuthUrl(state, input.clientId))
  } catch {
    isConnecting.value = false
    toasts.error(t('settings.integrations.strava.connectError'))
    // Best-effort: clear the half-set state so a retry starts clean.
    void clearStravaState().catch(() => undefined)
  }
}

function onRetrieveActivities(range: DateRange): void {
  activitiesMutation.mutate(range, {
    onSuccess: () => {
      isActivitiesOpen.value = false
      toasts.info(t('settings.integrations.strava.retrievingActivities'))
    },
    onError: () => toasts.error(t('settings.integrations.strava.retrieveActivitiesError')),
  })
}

function retrieveGear(): void {
  gearMutation.mutate(undefined, {
    onSuccess: () => toasts.info(t('settings.integrations.strava.retrievingGear')),
    onError: () => toasts.error(t('settings.integrations.strava.retrieveGearError')),
  })
}

function confirmUnlink(): void {
  unlinkMutation.mutate(undefined, {
    onSuccess: () => {
      isUnlinkOpen.value = false
      toasts.success(t('settings.integrations.strava.unlinkSuccess'))
    },
    onError: () => toasts.error(t('settings.integrations.strava.unlinkError')),
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

    <StravaConnectDialog
      v-model:open="isConnectOpen"
      :pending="isConnecting"
      @submit="connectStrava"
    />

    <RetrieveRangeDialog
      v-model:open="isActivitiesOpen"
      :title="t('settings.integrations.strava.retrieveActivitiesTitle')"
      :pending="activitiesMutation.isPending.value"
      @submit="onRetrieveActivities"
    />

    <ConfirmDialog
      v-model:open="isUnlinkOpen"
      :title="t('settings.integrations.strava.unlinkTitle')"
      :description="t('settings.integrations.strava.unlinkBody')"
      :confirm-label="t('settings.integrations.unlink')"
      :cancel-label="t('settings.integrations.cancel')"
      :close-label="t('settings.integrations.close')"
      :pending="unlinkMutation.isPending.value"
      @confirm="confirmUnlink"
    />
  </Card>
</template>
