<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ban } from '@lucide/vue'

import type { ApiKey, IdpReauth, StepUpInput } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import ApiKeyDetails from '@/features/security/components/ApiKeyDetails.vue'
import StepUpDialog from '@/features/security/components/StepUpDialog.vue'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useToasts } from '@/composables/useToasts'
import { isProblem } from '@/services/problems'
import {
  isStepUpFailed,
  isStepUpLocked,
  useIdpReauthChallenge,
} from '@/features/security/composables/useIdpStepUp'
import { useAdminStepUp, useResumeOnce } from '@/features/security/composables/useAdminStepUp'
import {
  useRevokeAllUserApiKeysMutation,
  useRevokeUserApiKeyMutation,
  useUserApiKeysQuery,
} from '@/features/users/composables/useUserApiKeys'

/**
 * The API keys card on the user detail page: the target user's API keys with a per-row
 * revoke action and a revoke-all action. Self-contained — it owns its query, the revoke
 * dialogs that collect the administrator's step-up, and the success/error toasts.
 */
const props = defineProps<{
  /** The user whose API keys to list. */
  userId: number
  /** The identity-provider sign-in the browser just returned from, if any. */
  resume: IdpStepUpResume | null
}>()

const { t } = useI18n()
const toasts = useToasts()

const userIdRef = computed(() => props.userId)
const { data, isPending, isError, refetch } = useUserApiKeysQuery(userIdRef)
const apiKeys = computed(() => data.value ?? [])
const hasActiveKeys = computed(() => apiKeys.value.some((key) => key.isActive))

const revokeMutation = useRevokeUserApiKeyMutation()
const isRevokeOpen = ref(false)
const keyToRevoke = ref<ApiKey | null>(null)
const revokeReauth = ref<IdpReauth | null>(null)

const revokeAllMutation = useRevokeAllUserApiKeysMutation()
const isRevokeAllOpen = ref(false)
const revokeAllReauth = ref<IdpReauth | null>(null)

const handleIdpChallenge = useIdpReauthChallenge()
const { requirePassword, requireMfa } = useAdminStepUp()

// Reopens the revoke dialog once the identity-provider sign-in returns, as soon as the key it was for
// is in the list.
useResumeOnce(
  () => props.resume,
  'admin_api_keys_revoke',
  (pending) =>
    pending.userId === props.userId &&
    typeof pending.apiKeyId === 'string' &&
    apiKeys.value.some((key) => key.id === pending.apiKeyId),
  (resume) => {
    keyToRevoke.value = apiKeys.value.find((key) => key.id === resume.pending.apiKeyId) ?? null
    revokeReauth.value = resume.reauth
    isRevokeOpen.value = true
  },
)
useResumeOnce(
  () => props.resume,
  'admin_api_keys_revoke',
  (pending) => pending.userId === props.userId && pending.all === true,
  (resume) => {
    revokeAllReauth.value = resume.reauth
    isRevokeAllOpen.value = true
  },
)

function openRevoke(key: ApiKey): void {
  keyToRevoke.value = key
  isRevokeOpen.value = true
}

/**
 * Reports a failed revoke; the dialog stays open on a refused step-up so it can be retried.
 *
 * @param error - The error the request failed with.
 * @param message - The message for any other failure.
 * @param dialogOpen - The dialog to close when the key no longer exists.
 */
function onRevokeError(error: unknown, message: string, dialogOpen?: typeof isRevokeOpen): void {
  if (handleIdpChallenge(error)) {
    return
  }
  if (isStepUpLocked(error)) {
    toasts.error(t('settings.security.stepUp.tooManyAttempts'))
  } else if (isStepUpFailed(error)) {
    toasts.error(t('settings.security.linked.invalidCredentials'))
  } else if (dialogOpen && isProblem(error, 'not-found')) {
    dialogOpen.value = false
    toasts.error(t('settings.users.apiKeys.revokeNotFound'))
  } else {
    toasts.error(message)
  }
}

/** Revokes the chosen key with the administrator's step-up. */
function confirmRevoke(stepUp: StepUpInput): void {
  const key = keyToRevoke.value
  if (!key) {
    return
  }
  revokeMutation.mutate(
    { apiKeyId: key.id, userId: props.userId, stepUp },
    {
      onSuccess: () => {
        isRevokeOpen.value = false
        toasts.success(t('settings.users.apiKeys.revokeSuccess'))
      },
      onError: (error) =>
        onRevokeError(error, t('settings.users.apiKeys.revokeError'), isRevokeOpen),
    },
  )
}

/** Revokes every active key of the user in a single request. */
function confirmRevokeAll(stepUp: StepUpInput): void {
  revokeAllMutation.mutate(
    { userId: props.userId, stepUp },
    {
      onSuccess: () => {
        isRevokeAllOpen.value = false
        toasts.success(t('settings.users.apiKeys.revokeAllSuccess'))
      },
      onError: (error) => onRevokeError(error, t('settings.users.apiKeys.revokeAllError')),
    },
  )
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-wrap items-start justify-between gap-2">
      <div class="flex flex-col gap-1">
        <h2 class="text-card-heading">{{ t('settings.users.apiKeys.title') }}</h2>
        <p class="text-hint">{{ t('settings.users.apiKeys.subtitle') }}</p>
      </div>
      <Button
        variant="outline"
        size="sm"
        :disabled="!hasActiveKeys"
        @click="isRevokeAllOpen = true"
      >
        {{ t('settings.users.apiKeys.revokeAll') }}
      </Button>
    </div>

    <!-- Loading -->
    <div v-if="isPending" class="flex flex-col gap-2" aria-busy="true">
      <Skeleton v-for="n in 2" :key="n" class="h-16 w-full rounded-input" />
    </div>

    <!-- Error -->
    <div v-else-if="isError" class="flex flex-col items-start gap-2">
      <p class="text-hint">{{ t('settings.users.apiKeys.error') }}</p>
      <Button variant="outline" size="sm" @click="() => refetch()">
        {{ t('settings.users.apiKeys.retry') }}
      </Button>
    </div>

    <!-- Empty -->
    <p v-else-if="apiKeys.length === 0" class="text-hint">
      {{ t('settings.users.apiKeys.empty') }}
    </p>

    <!-- List -->
    <ul v-else class="divide-y divide-border overflow-hidden rounded-card border border-border">
      <li
        v-for="key in apiKeys"
        :key="key.id"
        class="flex items-start justify-between gap-3 px-4 py-3"
      >
        <ApiKeyDetails :api-key="key" />
        <Button
          v-if="key.isActive"
          variant="ghost"
          size="icon-sm"
          class="shrink-0"
          :aria-label="t('settings.users.apiKeys.revoke')"
          @click="openRevoke(key)"
        >
          <Ban class="size-4" aria-hidden="true" />
        </Button>
      </li>
    </ul>

    <StepUpDialog
      v-model:open="isRevokeOpen"
      v-model:reauth="revokeReauth"
      action="admin_api_keys_revoke"
      :title="t('settings.users.apiKeys.revokeTitle')"
      :description="t('settings.users.apiKeys.revokeBody')"
      :confirm-label="t('settings.users.apiKeys.revokeConfirm')"
      :require-password="requirePassword"
      :require-mfa="requireMfa"
      :pending-context="{ userId, apiKeyId: keyToRevoke?.id }"
      destructive
      :pending="revokeMutation.isPending.value"
      @confirm="confirmRevoke"
    />

    <StepUpDialog
      v-model:open="isRevokeAllOpen"
      v-model:reauth="revokeAllReauth"
      action="admin_api_keys_revoke"
      :title="t('settings.users.apiKeys.revokeAllTitle')"
      :description="t('settings.users.apiKeys.revokeAllBody')"
      :confirm-label="t('settings.users.apiKeys.revokeAllConfirm')"
      :require-password="requirePassword"
      :require-mfa="requireMfa"
      :pending-context="{ userId, all: true }"
      destructive
      :pending="revokeAllMutation.isPending.value"
      @confirm="confirmRevokeAll"
    />
  </Card>
</template>
