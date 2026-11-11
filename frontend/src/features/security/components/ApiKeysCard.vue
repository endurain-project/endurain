<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ban, Plus, Trash2 } from '@lucide/vue'

import type { ApiKey, ApiKeyCreateInput, ApiKeyDraft, IdpReauth } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import ApiKeyDetails from '@/features/security/components/ApiKeyDetails.vue'
import ApiKeyCreateDialog from '@/features/security/components/ApiKeyCreateDialog.vue'
import ApiKeyRevealDialog from '@/features/security/components/ApiKeyRevealDialog.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { HttpError } from '@/services/http'
import { useToasts } from '@/composables/useToasts'
import { API_KEY_SCOPES, apiKeyExpiryInstant } from '@/features/security/services/security'
import {
  isStepUpFailed,
  isStepUpLocked,
  useIdpReauthChallenge,
} from '@/features/security/composables/useIdpStepUp'
import {
  useApiKeysQuery,
  useCreateApiKeyMutation,
  useDeleteApiKeyMutation,
  useRevokeApiKeyMutation,
} from '@/features/security/composables/useSecurity'

const props = defineProps<{
  /** Whether the account has a local password (gates the step-up password field). */
  hasLocalPassword: boolean
  /** Whether MFA is enabled (gates the step-up MFA-code field). */
  mfaEnabled: boolean
  /** The identity-provider sign-in the browser just returned from, if any. */
  resume: IdpStepUpResume | null
}>()

const { t } = useI18n()
const toasts = useToasts()

const { data, isPending, isError, refetch } = useApiKeysQuery()
const apiKeys = computed(() => data.value ?? [])

const createMutation = useCreateApiKeyMutation()
const revokeMutation = useRevokeApiKeyMutation()
const deleteMutation = useDeleteApiKeyMutation()

const handleIdpChallenge = useIdpReauthChallenge()

const isCreateOpen = ref(false)
const createReauth = ref<IdpReauth | null>(null)
const createDraft = ref<ApiKeyDraft | null>(null)
const isRevealOpen = ref(false)
const newApiKey = ref('')

// One shared confirm dialog per action drives every row (the pending target is
// held in a ref), mirroring SessionsCard.
const keyToRevoke = ref<ApiKey | null>(null)
const isRevokeOpen = ref(false)
const keyToDelete = ref<ApiKey | null>(null)
const isDeleteOpen = ref(false)

/** Reads the stored form values back, ignoring anything that is not the expected shape. */
function toDraft(pending: Record<string, unknown>): ApiKeyDraft {
  const { name, scopes, expiresAt } = pending
  return {
    name: typeof name === 'string' ? name : '',
    scopes: Array.isArray(scopes) ? API_KEY_SCOPES.filter((scope) => scopes.includes(scope)) : [],
    expiresAt: typeof expiresAt === 'string' ? expiresAt : null,
  }
}

/** Reopens the create dialog, with its form restored, once the identity-provider sign-in returns. */
onMounted(() => {
  if (props.resume?.action === 'api_key_create') {
    createDraft.value = toDraft(props.resume.pending)
    createReauth.value = props.resume.reauth
    isCreateOpen.value = true
  }
})

/** Whether the server refused the request with a 422 on the given field. */
function refusedField(error: unknown, field: string): boolean {
  return (
    error instanceof HttpError &&
    error.status === 422 &&
    error.errors.some((fieldError) => fieldError.field === field)
  )
}

/** Whether the server refused the scope list (`body.scopes`) or one entry of it (`body.scopes.<index>`). */
function refusedScope(error: unknown): boolean {
  return (
    error instanceof HttpError &&
    error.status === 422 &&
    error.errors.some((e) => e.field === 'body.scopes' || e.field.startsWith('body.scopes.'))
  )
}

/** Creates the key, then opens the one-time reveal dialog with the raw key. */
function onCreate(input: ApiKeyCreateInput): void {
  createMutation.mutate(input, {
    onSuccess: (rawKey) => {
      isCreateOpen.value = false
      createReauth.value = null
      createDraft.value = null
      newApiKey.value = rawKey
      isRevealOpen.value = true
      toasts.success(t('settings.security.apiKeys.createSuccess'))
    },
    onError: (error) => {
      if (handleIdpChallenge(error)) {
        return
      }
      if (isStepUpLocked(error)) {
        toasts.error(t('settings.security.stepUp.tooManyAttempts'))
      } else if (isStepUpFailed(error)) {
        toasts.error(t('settings.security.apiKeys.invalidCredentials'))
      } else if (refusedField(error, 'body.expires_at')) {
        // Both expiry refusals share the field and the error type, so the chosen date tells them apart.
        const isPast =
          input.expiresAt !== null && apiKeyExpiryInstant(input.expiresAt) <= new Date()
        toasts.error(
          t(
            isPast
              ? 'settings.security.apiKeys.expiryNotFuture'
              : 'settings.security.apiKeys.expiryTooLate',
          ),
        )
      } else if (refusedScope(error)) {
        toasts.error(t('settings.security.apiKeys.invalidScopes'))
      } else {
        toasts.error(t('settings.security.apiKeys.createError'))
      }
    },
  })
}

function openRevoke(key: ApiKey): void {
  keyToRevoke.value = key
  isRevokeOpen.value = true
}

function confirmRevoke(): void {
  const key = keyToRevoke.value
  if (!key) {
    return
  }
  revokeMutation.mutate(key.id, {
    onSuccess: () => {
      isRevokeOpen.value = false
      toasts.success(t('settings.security.apiKeys.revokeSuccess'))
    },
    onError: () => toasts.error(t('settings.security.apiKeys.revokeError')),
  })
}

function openDelete(key: ApiKey): void {
  keyToDelete.value = key
  isDeleteOpen.value = true
}

function confirmDelete(): void {
  const key = keyToDelete.value
  if (!key) {
    return
  }
  deleteMutation.mutate(key.id, {
    onSuccess: () => {
      isDeleteOpen.value = false
      toasts.success(t('settings.security.apiKeys.deleteSuccess'))
    },
    onError: () => toasts.error(t('settings.security.apiKeys.deleteError')),
  })
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-wrap items-start justify-between gap-2">
      <div class="flex flex-col gap-1">
        <h2 class="text-card-heading">{{ t('settings.security.apiKeys.title') }}</h2>
        <p class="text-hint">{{ t('settings.security.apiKeys.subtitle') }}</p>
      </div>
      <Button variant="outline" size="sm" @click="isCreateOpen = true">
        <Plus class="size-4" aria-hidden="true" />
        {{ t('settings.security.apiKeys.create') }}
      </Button>
    </div>

    <!-- Loading -->
    <div v-if="isPending" class="flex flex-col gap-2" aria-busy="true">
      <Skeleton v-for="n in 2" :key="n" class="h-16 w-full rounded-input" />
    </div>

    <!-- Error -->
    <div v-else-if="isError" class="flex flex-col items-start gap-2">
      <p class="text-hint">{{ t('settings.security.apiKeys.error') }}</p>
      <Button variant="outline" size="sm" @click="() => refetch()">
        {{ t('settings.security.retry') }}
      </Button>
    </div>

    <!-- Empty -->
    <p v-else-if="apiKeys.length === 0" class="text-hint">
      {{ t('settings.security.apiKeys.empty') }}
    </p>

    <!-- List -->
    <ul v-else class="divide-y divide-border overflow-hidden rounded-card border border-border">
      <li
        v-for="key in apiKeys"
        :key="key.id"
        class="flex items-start justify-between gap-3 px-4 py-3"
      >
        <ApiKeyDetails :api-key="key" />
        <div class="flex shrink-0 gap-1">
          <Button
            v-if="key.isActive"
            variant="ghost"
            size="icon-sm"
            :aria-label="t('settings.security.apiKeys.revoke')"
            @click="openRevoke(key)"
          >
            <Ban class="size-4" aria-hidden="true" />
          </Button>
          <Button
            variant="ghostDestructive"
            size="icon-sm"
            :aria-label="t('settings.security.apiKeys.delete')"
            @click="openDelete(key)"
          >
            <Trash2 class="size-4" aria-hidden="true" />
          </Button>
        </div>
      </li>
    </ul>

    <ApiKeyCreateDialog
      v-model:open="isCreateOpen"
      v-model:reauth="createReauth"
      :draft="createDraft"
      :require-password="hasLocalPassword"
      :require-mfa="mfaEnabled"
      :pending="createMutation.isPending.value"
      @submit="onCreate"
    />

    <ApiKeyRevealDialog v-model:open="isRevealOpen" :api-key="newApiKey" />

    <ConfirmDialog
      v-model:open="isRevokeOpen"
      :title="t('settings.security.apiKeys.revokeTitle')"
      :description="t('settings.security.apiKeys.revokeBody', { name: keyToRevoke?.name ?? '' })"
      :confirm-label="t('settings.security.apiKeys.revoke')"
      :cancel-label="t('settings.security.cancel')"
      :close-label="t('settings.security.close')"
      :pending="revokeMutation.isPending.value"
      confirm-variant="default"
      @confirm="confirmRevoke"
    />

    <ConfirmDialog
      v-model:open="isDeleteOpen"
      :title="t('settings.security.apiKeys.deleteTitle')"
      :description="t('settings.security.apiKeys.deleteBody', { name: keyToDelete?.name ?? '' })"
      :confirm-label="t('settings.security.apiKeys.delete')"
      :cancel-label="t('settings.security.cancel')"
      :close-label="t('settings.security.close')"
      :pending="deleteMutation.isPending.value"
      @confirm="confirmDelete"
    />
  </Card>
</template>
