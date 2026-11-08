<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { Monitor, Trash2 } from '@lucide/vue'

import type { SecuritySession } from '@/features/security/types'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useToasts } from '@/composables/useToasts'
import { formatMediumDateTime } from '@/utils/datetime'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  useRevokeOtherSessionsMutation,
  useRevokeSessionMutation,
  useSessionsQuery,
  useSignOutEverywhereMutation,
} from '@/features/security/composables/useSecurity'

/**
 * The Sessions card: the authenticated user's active sessions with a per-row
 * revoke action. The current session is badged and cannot be revoked here
 * (sign out to end it); revoke other devices in bulk via the change-password
 * form's "sign out other sessions" option.
 */
const { t, locale } = useI18n()
const toasts = useToasts()
const { sessionId } = storeToRefs(useAuthStore())

const { data, isPending, isError, refetch } = useSessionsQuery()
const sessions = computed(() => data.value ?? [])

const revokeMutation = useRevokeSessionMutation()
const isConfirmOpen = ref(false)
const sessionToRevoke = ref<SecuritySession | null>(null)

const revokeOthersMutation = useRevokeOtherSessionsMutation()
const isRevokeOthersOpen = ref(false)

const signOutEverywhereMutation = useSignOutEverywhereMutation()
const isSignOutEverywhereOpen = ref(false)

/** Whether a session is the signed-in user's own current session. */
function isCurrent(session: SecuritySession): boolean {
  return session.id === sessionId.value
}

/** The number of sessions that aren't the current one (revocable in bulk). */
const otherSessionsCount = computed(
  () => sessions.value.filter((session) => !isCurrent(session)).length,
)

/** A device label built from browser + OS, falling back to the device type. */
function sessionLabel(session: SecuritySession): string {
  const browser = [session.browser, session.browserVersion].filter(Boolean).join(' ')
  const os = [session.operatingSystem, session.operatingSystemVersion].filter(Boolean).join(' ')
  return [browser, os].filter(Boolean).join(' · ') || session.deviceType
}

/** Formats an ISO timestamp in the active locale, or `''` when unparseable. */
function formatDate(iso: string): string {
  return formatMediumDateTime(iso, locale.value)
}

function openRevoke(session: SecuritySession): void {
  sessionToRevoke.value = session
  isConfirmOpen.value = true
}

function confirmRevoke(): void {
  const session = sessionToRevoke.value
  if (!session) {
    return
  }
  revokeMutation.mutate(session.id, {
    onSuccess: () => {
      isConfirmOpen.value = false
      toasts.success(t('settings.security.sessions.revokeSuccess'))
    },
    onError: () => toasts.error(t('settings.security.sessions.revokeError')),
  })
}

/** Revokes every session except the current one (kept server-side via the token). */
function confirmRevokeOthers(): void {
  revokeOthersMutation.mutate(undefined, {
    onSuccess: () => {
      isRevokeOthersOpen.value = false
      toasts.success(t('settings.security.sessions.revokeOthersSuccess'))
    },
    onError: () => toasts.error(t('settings.security.sessions.revokeOthersError')),
  })
}

/** Ends every session including this one; the mutation then leaves for the login page. */
function confirmSignOutEverywhere(): void {
  signOutEverywhereMutation.mutate(undefined, {
    onError: () => toasts.error(t('settings.security.sessions.signOutEverywhereError')),
  })
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-wrap items-start justify-between gap-2">
      <div class="flex flex-col gap-1">
        <h2 class="text-card-heading">{{ t('settings.security.sessions.title') }}</h2>
        <p class="text-hint">{{ t('settings.security.sessions.subtitle') }}</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <Button
          v-if="otherSessionsCount > 0"
          variant="outline"
          size="sm"
          @click="isRevokeOthersOpen = true"
        >
          {{ t('settings.security.sessions.revokeOthers') }}
        </Button>
        <Button variant="outline" size="sm" @click="isSignOutEverywhereOpen = true">
          {{ t('settings.security.sessions.signOutEverywhere') }}
        </Button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isPending" class="flex flex-col gap-2" aria-busy="true">
      <Skeleton v-for="n in 2" :key="n" class="h-14 w-full rounded-input" />
    </div>

    <!-- Error -->
    <div v-else-if="isError" class="flex flex-col items-start gap-2">
      <p class="text-hint">{{ t('settings.security.sessions.error') }}</p>
      <Button variant="outline" size="sm" @click="() => refetch()">
        {{ t('settings.security.retry') }}
      </Button>
    </div>

    <!-- Empty -->
    <p v-else-if="sessions.length === 0" class="text-hint">
      {{ t('settings.security.sessions.empty') }}
    </p>

    <!-- List -->
    <ul v-else class="divide-y divide-border overflow-hidden rounded-card border border-border">
      <li
        v-for="session in sessions"
        :key="session.id"
        class="flex items-center justify-between gap-3 px-4 py-3"
      >
        <div class="flex min-w-0 items-center gap-3">
          <Monitor class="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div class="min-w-0">
            <div class="flex min-w-0 items-center gap-2">
              <p class="text-body">{{ sessionLabel(session) }}</p>
              <Badge v-if="isCurrent(session)" variant="secondary" class="shrink-0">
                {{ t('settings.security.sessions.current') }}
              </Badge>
            </div>
            <p class="text-hint">
              {{ session.ipAddress }} ·
              {{
                t('settings.security.sessions.lastActive', {
                  date: formatDate(session.lastActivityAt),
                })
              }}
            </p>
          </div>
        </div>
        <Button
          variant="ghostDestructive"
          size="icon-sm"
          :disabled="isCurrent(session)"
          :aria-label="t('settings.security.sessions.revoke')"
          @click="openRevoke(session)"
        >
          <Trash2 class="size-4" aria-hidden="true" />
        </Button>
      </li>
    </ul>

    <ConfirmDialog
      v-model:open="isConfirmOpen"
      :title="t('settings.security.sessions.revokeTitle')"
      :description="t('settings.security.sessions.revokeBody')"
      :confirm-label="t('settings.security.sessions.revokeConfirm')"
      :cancel-label="t('settings.security.cancel')"
      :close-label="t('settings.security.close')"
      :pending="revokeMutation.isPending.value"
      @confirm="confirmRevoke"
    />

    <ConfirmDialog
      v-model:open="isRevokeOthersOpen"
      :title="t('settings.security.sessions.revokeOthersTitle')"
      :description="t('settings.security.sessions.revokeOthersBody')"
      :confirm-label="t('settings.security.sessions.revokeOthersConfirm')"
      :cancel-label="t('settings.security.cancel')"
      :close-label="t('settings.security.close')"
      :pending="revokeOthersMutation.isPending.value"
      @confirm="confirmRevokeOthers"
    />

    <ConfirmDialog
      v-model:open="isSignOutEverywhereOpen"
      :title="t('settings.security.sessions.signOutEverywhereTitle')"
      :description="t('settings.security.sessions.signOutEverywhereBody')"
      :confirm-label="t('settings.security.sessions.signOutEverywhereConfirm')"
      :cancel-label="t('settings.security.cancel')"
      :close-label="t('settings.security.close')"
      :pending="signOutEverywhereMutation.isPending.value"
      @confirm="confirmSignOutEverywhere"
    />
  </Card>
</template>
