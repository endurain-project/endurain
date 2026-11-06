<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ManagedUser } from '@/features/users/types'
import type { IdpReauth, StepUpInput } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import StepUpDialog from '@/features/security/components/StepUpDialog.vue'
import { useToasts } from '@/composables/useToasts'
import { isStaleWrite } from '@/services/ifMatch'
import { isStepUpFailed, useIdpReauthChallenge } from '@/features/security/composables/useIdpStepUp'
import { useAdminStepUp, useResumeOnce } from '@/features/users/composables/useAdminStepUp'
import { useDeleteUserMutation } from '@/features/users/composables/useUsers'

const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  /** The user to delete, or `null` while none is chosen. */
  user: ManagedUser | null
  /** `delete` removes an account; `reject` removes a pending sign-up. Only the copy differs. */
  variant: 'delete' | 'reject'
  /** The identity-provider sign-in the browser just returned from, if any. */
  resume: IdpStepUpResume | null
}>()

const emit = defineEmits<{
  /** The deletion was queued. */
  success: []
}>()

const { t } = useI18n()
const toasts = useToasts()
const mutation = useDeleteUserMutation()
const handleIdpChallenge = useIdpReauthChallenge()
const { requirePassword, requireMfa } = useAdminStepUp()

const idpReauth = ref<IdpReauth | null>(null)

// Reopens the dialog once the identity-provider sign-in returns for this user.
useResumeOnce(
  () => props.resume,
  'admin_user_delete',
  () => props.user?.id ?? null,
  (resume) => {
    idpReauth.value = resume.reauth
    open.value = true
  },
  (pending) => pending.variant === props.variant,
)

const copy = computed(() =>
  props.variant === 'reject'
    ? {
        title: t('settings.users.approval.rejectTitle'),
        description: t('settings.users.approval.rejectBody', {
          username: props.user?.username ?? '',
        }),
        confirm: t('settings.users.approval.rejectConfirm'),
        success: t('settings.users.approval.rejectSuccess'),
        error: t('settings.users.approval.rejectError'),
      }
    : {
        title: t('settings.users.delete.title'),
        description: t('settings.users.delete.body', { name: props.user?.name ?? '' }),
        confirm: t('settings.users.delete.confirm'),
        success: t('settings.users.delete.success'),
        error: t('settings.users.delete.error'),
      },
)

/** Queues the deletion with the administrator's step-up; the dialog stays open on a refused step-up. */
function onConfirm(stepUp: StepUpInput): void {
  const target = props.user
  if (!target) {
    return
  }
  mutation.mutate(
    { id: target.id, version: target.version, stepUp },
    {
      onSuccess: () => {
        open.value = false
        toasts.success(copy.value.success)
        emit('success')
      },
      onError: (error) => {
        if (handleIdpChallenge(error)) {
          return
        }
        if (isStepUpFailed(error)) {
          toasts.error(t('settings.security.linked.invalidCredentials'))
          return
        }
        if (isStaleWrite(error)) {
          open.value = false
        }
        toasts.error(isStaleWrite(error) ? t('app.staleError') : copy.value.error)
      },
    },
  )
}
</script>

<template>
  <StepUpDialog
    v-model:open="open"
    v-model:reauth="idpReauth"
    action="admin_user_delete"
    :title="copy.title"
    :description="copy.description"
    :confirm-label="copy.confirm"
    :require-password="requirePassword"
    :require-mfa="requireMfa"
    :pending-context="{ userId: user?.id, variant }"
    destructive
    :pending="mutation.isPending.value"
    @confirm="onConfirm"
  />
</template>
