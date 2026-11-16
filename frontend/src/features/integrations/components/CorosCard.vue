<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown } from '@lucide/vue'

import type { CorosStatus, DateRange } from '@/features/integrations/types'

import RetrieveRangeDialog from '@/features/integrations/components/RetrieveRangeDialog.vue'
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
  useCorosStatusQuery,
  useSyncCorosMutation,
  useUnlinkCorosMutation,
} from '@/features/integrations/composables/useIntegrations'
import { startCorosAuthorization } from '@/features/integrations/services/coros'
import { formatMediumDateTime } from '@/utils/datetime'

const props = defineProps<{
  /** Whether a COROS account is currently connected. */
  linked: boolean
}>()

const { t, te, locale } = useI18n()
const toasts = useToasts()

const statusQuery = useCorosStatusQuery(() => props.linked)
const syncMutation = useSyncCorosMutation()
const unlinkMutation = useUnlinkCorosMutation()

const isConnecting = ref(false)
const isActivitiesOpen = ref(false)
const isUnlinkOpen = ref(false)

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
    onSuccess: () => toasts.info(t('settings.integrations.coros.syncQueued')),
    onError: () => toasts.error(t('settings.integrations.coros.syncError')),
  })
}

function onRetrieveActivities(range: DateRange): void {
  syncMutation.mutate(range, {
    onSuccess: () => {
      isActivitiesOpen.value = false
      toasts.info(t('settings.integrations.coros.syncQueued'))
    },
    onError: () => toasts.error(t('settings.integrations.coros.syncError')),
  })
}

function confirmUnlink(): void {
  unlinkMutation.mutate(undefined, {
    onSuccess: () => {
      isUnlinkOpen.value = false
      toasts.success(t('settings.integrations.coros.unlinkSuccess'))
    },
    onError: () => toasts.error(t('settings.integrations.coros.unlinkError')),
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

    <ConfirmDialog
      v-model:open="isUnlinkOpen"
      :title="t('settings.integrations.coros.unlinkTitle')"
      :description="t('settings.integrations.coros.unlinkBody')"
      :confirm-label="t('settings.integrations.unlink')"
      :cancel-label="t('settings.integrations.cancel')"
      :close-label="t('settings.integrations.close')"
      :pending="unlinkMutation.isPending.value"
      @confirm="confirmUnlink"
    />
  </Card>
</template>
