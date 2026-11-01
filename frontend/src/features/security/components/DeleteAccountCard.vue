<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Trash2 } from '@lucide/vue'

import type { IdpReauth, StepUpInput } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import StepUpDialog from '@/features/security/components/StepUpDialog.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useToasts } from '@/composables/useToasts'
import { HttpError } from '@/services/http'
import { useIdpReauthChallenge } from '@/features/security/composables/useIdpStepUp'
import { useDeleteAccountMutation } from '@/features/security/composables/useSecurity'

const props = defineProps<{
  /** The account's username; the user types it to confirm the deletion. */
  username: string
  /** Whether the account has a local password (gates the step-up password field). */
  hasLocalPassword: boolean
  /** Whether MFA is enabled (gates the step-up MFA-code field). */
  mfaEnabled: boolean
  /** The identity-provider sign-in the browser just returned from, if any. */
  resume: IdpStepUpResume | null
}>()

const { t } = useI18n()
const toasts = useToasts()
const deleteMutation = useDeleteAccountMutation()
const handleIdpChallenge = useIdpReauthChallenge()

const isDialogOpen = ref(false)
const idpReauth = ref<IdpReauth | null>(null)

/** Reopens the dialog once the identity-provider sign-in returns. */
onMounted(() => {
  if (props.resume?.action === 'account_delete') {
    idpReauth.value = props.resume.reauth
    isDialogOpen.value = true
  }
})

/** Deletes the account after step-up; the mutation leaves for the farewell page. */
function onConfirm(input: StepUpInput): void {
  deleteMutation.mutate(input, {
    onError: (error) => {
      if (handleIdpChallenge(error)) {
        return
      }
      if (error instanceof HttpError && error.status === 409) {
        toasts.error(t('settings.security.deleteAccount.onlyAdminError'))
      } else if (error instanceof HttpError && error.status === 401) {
        toasts.error(t('settings.security.linked.invalidCredentials'))
      } else {
        toasts.error(t('settings.security.deleteAccount.error'))
      }
    },
  })
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-col gap-1">
      <h2 class="text-card-heading">{{ t('settings.security.deleteAccount.title') }}</h2>
      <p class="text-hint">{{ t('settings.security.deleteAccount.subtitle') }}</p>
    </div>

    <div>
      <Button variant="destructive" @click="isDialogOpen = true">
        <Trash2 class="size-4" aria-hidden="true" />
        <span>{{ t('settings.security.deleteAccount.action') }}</span>
      </Button>
    </div>

    <StepUpDialog
      v-model:open="isDialogOpen"
      v-model:reauth="idpReauth"
      action="account_delete"
      :title="t('settings.security.deleteAccount.dialogTitle')"
      :description="t('settings.security.deleteAccount.dialogDescription')"
      :confirm-label="t('settings.security.deleteAccount.confirm')"
      :require-password="props.hasLocalPassword"
      :require-mfa="props.mfaEnabled"
      :confirm-phrase="props.username"
      :restored-context="
        props.resume?.action === 'account_delete' ? props.resume.pending : undefined
      "
      destructive
      :pending="deleteMutation.isPending.value"
      @confirm="onConfirm"
    />
  </Card>
</template>
