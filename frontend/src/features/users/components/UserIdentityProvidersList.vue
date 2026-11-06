<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ShieldCheck, Unlink } from '@lucide/vue'

import type { UserIdentityProvider } from '@/features/users/types'
import type { IdpReauth, StepUpInput } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import StepUpDialog from '@/features/security/components/StepUpDialog.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useToasts } from '@/composables/useToasts'
import { HttpError } from '@/services/http'
import { formatMediumDate } from '@/utils/datetime'
import { isStepUpFailed, useIdpReauthChallenge } from '@/features/security/composables/useIdpStepUp'
import { useAdminStepUp, useResumeOnce } from '@/features/security/composables/useAdminStepUp'
import {
  useUnlinkUserIdentityProviderMutation,
  useUserIdentityProvidersQuery,
} from '@/features/users/composables/useUserIdentityProviders'

/**
 * The Identity providers card on the user detail page: the target user's linked
 * single sign-on accounts with a per-row unlink action. Self-contained — it owns
 * its query, the unlink-confirmation dialog, and the success/error toasts.
 */
const props = defineProps<{
  /** The user whose identity-provider links to list. */
  userId: number
  /** The identity-provider sign-in the browser just returned from, if any. */
  resume: IdpStepUpResume | null
}>()

const { t, locale } = useI18n()
const toasts = useToasts()

const userIdRef = computed(() => props.userId)
const { data, isPending, isError, refetch } = useUserIdentityProvidersQuery(userIdRef)
const providers = computed(() => data.value ?? [])

const unlinkMutation = useUnlinkUserIdentityProviderMutation()
const isConfirmOpen = ref(false)
const providerToUnlink = ref<UserIdentityProvider | null>(null)
const idpReauth = ref<IdpReauth | null>(null)
const handleIdpChallenge = useIdpReauthChallenge()
const { requirePassword, requireMfa } = useAdminStepUp()

// Reopens the unlink dialog once the identity-provider sign-in returns, as soon as the provider it was for
// is in the list.
useResumeOnce(
  () => props.resume,
  'admin_idp_unlink',
  (pending) =>
    pending.userId === props.userId &&
    providers.value.some((provider) => provider.idpId === pending.idpId),
  (resume) => {
    providerToUnlink.value =
      providers.value.find((provider) => provider.idpId === resume.pending.idpId) ?? null
    idpReauth.value = resume.reauth
    isConfirmOpen.value = true
  },
)

/** A display name for a provider, falling back to its slug. */
function providerLabel(provider: UserIdentityProvider): string {
  return provider.name || provider.slug || t('settings.users.identityProviders.unknownProvider')
}

/** Formats an ISO timestamp in the active locale, or `''` when unparseable. */
function formatDate(iso: string): string {
  return formatMediumDate(iso, locale.value)
}

function openUnlink(provider: UserIdentityProvider): void {
  providerToUnlink.value = provider
  isConfirmOpen.value = true
}

function confirmUnlink(stepUp: StepUpInput): void {
  const provider = providerToUnlink.value
  if (!provider) {
    return
  }
  unlinkMutation.mutate(
    { userId: props.userId, idpId: provider.idpId, stepUp },
    {
      onSuccess: () => {
        isConfirmOpen.value = false
        toasts.success(t('settings.users.identityProviders.unlinkSuccess'))
      },
      onError: (error) => {
        if (handleIdpChallenge(error)) {
          return
        }
        if (isStepUpFailed(error)) {
          toasts.error(t('settings.security.linked.invalidCredentials'))
          return
        }
        // 400 = the backend guard against removing the user's last auth method.
        toasts.error(
          error instanceof HttpError && error.status === 400
            ? t('settings.users.identityProviders.unlinkLastError')
            : t('settings.users.identityProviders.unlinkError'),
        )
      },
    },
  )
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-col gap-1">
      <h2 class="text-card-heading">{{ t('settings.users.identityProviders.title') }}</h2>
      <p class="text-hint">{{ t('settings.users.identityProviders.subtitle') }}</p>
    </div>

    <!-- Loading -->
    <div v-if="isPending" class="flex flex-col gap-2" aria-busy="true">
      <Skeleton v-for="n in 2" :key="n" class="h-14 w-full rounded-input" />
    </div>

    <!-- Error -->
    <div v-else-if="isError" class="flex flex-col items-start gap-2">
      <p class="text-hint">{{ t('settings.users.identityProviders.error') }}</p>
      <Button variant="outline" size="sm" @click="() => refetch()">
        {{ t('settings.users.identityProviders.retry') }}
      </Button>
    </div>

    <!-- Empty -->
    <p v-else-if="providers.length === 0" class="text-hint">
      {{ t('settings.users.identityProviders.empty') }}
    </p>

    <!-- List -->
    <ul v-else class="divide-y divide-border overflow-hidden rounded-card border border-border">
      <li
        v-for="provider in providers"
        :key="provider.id"
        class="flex items-center justify-between gap-3 px-4 py-3"
      >
        <div class="flex min-w-0 items-center gap-3">
          <ShieldCheck class="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div class="min-w-0">
            <div class="flex min-w-0 items-center gap-2">
              <p class="truncate text-body">{{ providerLabel(provider) }}</p>
              <Badge v-if="provider.providerType" variant="secondary" class="shrink-0">
                {{ provider.providerType }}
              </Badge>
            </div>
            <p class="truncate text-hint">
              {{ provider.subject }} ·
              {{
                t('settings.users.identityProviders.linkedAt', {
                  date: formatDate(provider.linkedAt),
                })
              }}
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          :aria-label="t('settings.users.identityProviders.unlink')"
          @click="openUnlink(provider)"
        >
          <Unlink class="size-4" aria-hidden="true" />
        </Button>
      </li>
    </ul>

    <StepUpDialog
      v-model:open="isConfirmOpen"
      v-model:reauth="idpReauth"
      action="admin_idp_unlink"
      :title="t('settings.users.identityProviders.unlinkTitle')"
      :description="
        t('settings.users.identityProviders.unlinkBody', {
          provider: providerToUnlink ? providerLabel(providerToUnlink) : '',
        })
      "
      :confirm-label="t('settings.users.identityProviders.unlinkConfirm')"
      :require-password="requirePassword"
      :require-mfa="requireMfa"
      :pending-context="{ userId, idpId: providerToUnlink?.idpId }"
      destructive
      :pending="unlinkMutation.isPending.value"
      @confirm="confirmUnlink"
    />
  </Card>
</template>
