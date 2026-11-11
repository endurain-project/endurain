<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { Monitor, Trash2 } from '@lucide/vue'

import type { UserSession } from '@/features/users/types'
import type { IdpReauth, StepUpInput } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import StepUpDialog from '@/features/security/components/StepUpDialog.vue'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useToasts } from '@/composables/useToasts'
import { formatMediumDateTime } from '@/utils/datetime'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  isStepUpFailed,
  isStepUpLocked,
  useIdpReauthChallenge,
} from '@/features/security/composables/useIdpStepUp'
import { useAdminStepUp, useResumeOnce } from '@/features/security/composables/useAdminStepUp'
import {
  useRevokeOtherUserSessionsMutation,
  useRevokeUserSessionMutation,
  useUserSessionsQuery,
} from '@/features/users/composables/useUserSessions'

/**
 * The Sessions card on the user detail page: the target user's active sessions
 * with a per-row revoke action. Self-contained — it owns its query, the
 * revoke dialogs that collect the administrator's step-up, and the success/error toasts.
 */
const props = defineProps<{
  /** The user whose sessions to list. */
  userId: number
  /** The identity-provider sign-in the browser just returned from, if any. */
  resume: IdpStepUpResume | null
}>()

const { t, locale } = useI18n()
const toasts = useToasts()
const { sessionId } = storeToRefs(useAuthStore())

const userIdRef = computed(() => props.userId)
const { data, isPending, isError, refetch } = useUserSessionsQuery(userIdRef)
const sessions = computed(() => data.value ?? [])

/** Whether a session is the signed-in admin's own current session (no self-revoke). */
function isCurrent(session: UserSession): boolean {
  return session.id === sessionId.value
}

const revokeMutation = useRevokeUserSessionMutation()

const isConfirmOpen = ref(false)
const sessionToRevoke = ref<UserSession | null>(null)
const revokeReauth = ref<IdpReauth | null>(null)

const revokeOthersMutation = useRevokeOtherUserSessionsMutation()
const isRevokeOthersOpen = ref(false)
const revokeOthersReauth = ref<IdpReauth | null>(null)

const handleIdpChallenge = useIdpReauthChallenge()
const { requirePassword, requireMfa } = useAdminStepUp()

// Reopens the revoke dialog once the identity-provider sign-in returns, as soon as the session it was for
// is in the list.
useResumeOnce(
  () => props.resume,
  'admin_sessions_revoke',
  (pending) =>
    pending.userId === props.userId &&
    typeof pending.sessionId === 'string' &&
    sessions.value.some((session) => session.id === pending.sessionId),
  (resume) => {
    sessionToRevoke.value =
      sessions.value.find((session) => session.id === resume.pending.sessionId) ?? null
    revokeReauth.value = resume.reauth
    isConfirmOpen.value = true
  },
)
useResumeOnce(
  () => props.resume,
  'admin_sessions_revoke',
  (pending) => pending.userId === props.userId && pending.others === true,
  (resume) => {
    revokeOthersReauth.value = resume.reauth
    isRevokeOthersOpen.value = true
  },
)

/** Sessions that aren't the admin's current one (i.e. revocable in bulk). */
const otherSessionsCount = computed(
  () => sessions.value.filter((session) => !isCurrent(session)).length,
)

/** A device label built from browser + OS, falling back to the device type. */
function sessionLabel(session: UserSession): string {
  const browser = [session.browser, session.browserVersion].filter(Boolean).join(' ')
  const os = [session.operatingSystem, session.operatingSystemVersion].filter(Boolean).join(' ')
  return [browser, os].filter(Boolean).join(' · ') || session.deviceType
}

/** Formats an ISO timestamp in the active locale, or `''` when unparseable. */
function formatDate(iso: string): string {
  return formatMediumDateTime(iso, locale.value)
}

function openRevoke(session: UserSession): void {
  sessionToRevoke.value = session
  isConfirmOpen.value = true
}

/**
 * Reports a failed revoke; the dialog stays open on a refused step-up so it can be retried.
 *
 * @param error - The error the request failed with.
 * @param message - The message for any other failure.
 */
function onRevokeError(error: unknown, message: string): void {
  if (handleIdpChallenge(error)) {
    return
  }
  if (isStepUpLocked(error)) {
    toasts.error(t('settings.security.stepUp.tooManyAttempts'))
    return
  }
  toasts.error(isStepUpFailed(error) ? t('settings.security.linked.invalidCredentials') : message)
}

/** Revokes the chosen session with the administrator's step-up. */
function confirmRevoke(stepUp: StepUpInput): void {
  const session = sessionToRevoke.value
  if (!session) {
    return
  }
  revokeMutation.mutate(
    { sessionId: session.id, userId: props.userId, stepUp },
    {
      onSuccess: () => {
        isConfirmOpen.value = false
        toasts.success(t('settings.users.sessions.revokeSuccess'))
      },
      onError: (error) => onRevokeError(error, t('settings.users.sessions.revokeError')),
    },
  )
}

/** Revokes every session except the caller's current one, in a single request. */
function confirmRevokeOthers(stepUp: StepUpInput): void {
  revokeOthersMutation.mutate(
    { userId: props.userId, stepUp, excludeSessionId: sessionId.value ?? undefined },
    {
      onSuccess: () => {
        isRevokeOthersOpen.value = false
        toasts.success(t('settings.users.sessions.revokeOthersSuccess'))
      },
      onError: (error) => onRevokeError(error, t('settings.users.sessions.revokeOthersError')),
    },
  )
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-wrap items-start justify-between gap-2">
      <div class="flex flex-col gap-1">
        <h2 class="text-card-heading">{{ t('settings.users.sessions.title') }}</h2>
        <p class="text-hint">{{ t('settings.users.sessions.subtitle') }}</p>
      </div>
      <Button
        v-if="otherSessionsCount > 0"
        variant="outline"
        size="sm"
        @click="isRevokeOthersOpen = true"
      >
        {{ t('settings.users.sessions.revokeOthers') }}
      </Button>
    </div>

    <!-- Loading -->
    <div v-if="isPending" class="flex flex-col gap-2" aria-busy="true">
      <Skeleton v-for="n in 2" :key="n" class="h-14 w-full rounded-input" />
    </div>

    <!-- Error -->
    <div v-else-if="isError" class="flex flex-col items-start gap-2">
      <p class="text-hint">{{ t('settings.users.sessions.error') }}</p>
      <Button variant="outline" size="sm" @click="() => refetch()">
        {{ t('settings.users.sessions.retry') }}
      </Button>
    </div>

    <!-- Empty -->
    <p v-else-if="sessions.length === 0" class="text-hint">
      {{ t('settings.users.sessions.empty') }}
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
              <p class="truncate text-body">{{ sessionLabel(session) }}</p>
              <Badge v-if="isCurrent(session)" variant="secondary" class="shrink-0">
                {{ t('settings.users.sessions.current') }}
              </Badge>
            </div>
            <p class="truncate text-hint">
              {{ session.ipAddress }} ·
              {{
                t('settings.users.sessions.lastActive', {
                  date: formatDate(session.lastActivityAt),
                })
              }}
            </p>
            <p v-if="session.appRedirectUri" class="truncate text-hint">
              {{ t('settings.users.sessions.viaApp', { address: session.appRedirectUri }) }}
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          :disabled="isCurrent(session)"
          :aria-label="t('settings.users.sessions.revoke')"
          @click="openRevoke(session)"
        >
          <Trash2 class="size-4" aria-hidden="true" />
        </Button>
      </li>
    </ul>

    <StepUpDialog
      v-model:open="isConfirmOpen"
      v-model:reauth="revokeReauth"
      action="admin_sessions_revoke"
      :title="t('settings.users.sessions.revokeTitle')"
      :description="t('settings.users.sessions.revokeBody')"
      :confirm-label="t('settings.users.sessions.revokeConfirm')"
      :require-password="requirePassword"
      :require-mfa="requireMfa"
      :pending-context="{ userId, sessionId: sessionToRevoke?.id }"
      destructive
      :pending="revokeMutation.isPending.value"
      @confirm="confirmRevoke"
    />

    <StepUpDialog
      v-model:open="isRevokeOthersOpen"
      v-model:reauth="revokeOthersReauth"
      action="admin_sessions_revoke"
      :title="t('settings.users.sessions.revokeOthersTitle')"
      :description="t('settings.users.sessions.revokeOthersBody')"
      :confirm-label="t('settings.users.sessions.revokeOthersConfirm')"
      :require-password="requirePassword"
      :require-mfa="requireMfa"
      :pending-context="{ userId, others: true }"
      destructive
      :pending="revokeOthersMutation.isPending.value"
      @confirm="confirmRevokeOthers"
    />
  </Card>
</template>
