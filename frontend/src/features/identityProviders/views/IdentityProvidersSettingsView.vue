<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { KeyRound, Plus } from '@lucide/vue'

import type { IdentityProvider } from '@/features/identityProviders/types'
import type { IdpReauth, StepUpInput } from '@/features/security/types'

import IdentityProviderFormDialog from '@/features/identityProviders/components/IdentityProviderFormDialog.vue'
import IdentityProviderListItem from '@/features/identityProviders/components/IdentityProviderListItem.vue'
import StepUpDialog from '@/features/security/components/StepUpDialog.vue'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { ListPanel } from '@/components/ui/list-panel'
import { useToasts } from '@/composables/useToasts'
import { HttpError } from '@/services/http'
import { isStaleWrite } from '@/services/ifMatch'
import { resumeTargetId, useAdminStepUp } from '@/features/security/composables/useAdminStepUp'
import {
  consumeIdpStepUpReturn,
  isStepUpFailed,
  isStepUpLocked,
  useIdpReauthChallenge,
} from '@/features/security/composables/useIdpStepUp'
import { toProviderInput } from '@/features/identityProviders/services/identityProviders'
import {
  useDeleteIdentityProviderMutation,
  useIdentityProvidersQuery,
  useIdentityProviderTemplatesQuery,
  useUpdateIdentityProviderMutation,
} from '@/features/identityProviders/composables/useIdentityProviders'

const { t } = useI18n()
const toasts = useToasts()

// Returning from an identity-provider sign-in, the callback leaves its outcome in the URL fragment. It is
// consumed once; the dialog that started it reopens, and a failure is reported once the page is shown.
const stepUpReturn = consumeIdpStepUpReturn()
const resume = stepUpReturn && !stepUpReturn.error ? stepUpReturn : null
onMounted(() => {
  if (stepUpReturn?.error === 'not_fresh') {
    toasts.error(t('settings.security.stepUp.notFresh'))
  } else if (stepUpReturn?.error) {
    toasts.error(t('settings.security.stepUp.failed'))
  }
})
const handleIdpChallenge = useIdpReauthChallenge()
const { requirePassword, requireMfa } = useAdminStepUp()

const providersQuery = useIdentityProvidersQuery()
const templatesQuery = useIdentityProviderTemplatesQuery()
const updateMutation = useUpdateIdentityProviderMutation()
const deleteMutation = useDeleteIdentityProviderMutation()

const providers = computed(() => providersQuery.data.value ?? [])
const templates = computed(() => templatesQuery.data.value ?? [])
const isEmpty = computed(
  () =>
    !providersQuery.isPending.value &&
    !providersQuery.isError.value &&
    providers.value.length === 0,
)

// Add/edit dialog state. A `null` target means "add".
const isFormOpen = ref(false)
const providerToEdit = ref<IdentityProvider | null>(null)

/** Opens the dialog in add mode. */
function openAdd(): void {
  providerToEdit.value = null
  isFormOpen.value = true
}

/** Opens the dialog in edit mode for the given provider. */
function openEdit(provider: IdentityProvider): void {
  providerToEdit.value = provider
  isFormOpen.value = true
}

// Delete state. Removing a provider needs the administrator's step-up, collected by the dialog.
const isDeleteOpen = ref(false)
const providerToDelete = ref<IdentityProvider | null>(null)
const deleteReauth = ref<IdpReauth | null>(null)

/** Opens the delete step-up dialog for the given provider. */
function openDelete(provider: IdentityProvider): void {
  providerToDelete.value = provider
  isDeleteOpen.value = true
}

/**
 * Deletes the pending provider with the administrator's step-up; the backend blocks deletion of linked
 * providers, and a refused step-up keeps the dialog open for another try.
 *
 * @param stepUp - The administrator's step-up from the dialog.
 */
function confirmDelete(stepUp: StepUpInput): void {
  const provider = providerToDelete.value
  if (!provider) {
    return
  }
  deleteMutation.mutate(
    { id: provider.id, version: provider.version, stepUp },
    {
      onSuccess: () => {
        isDeleteOpen.value = false
        toasts.success(t('settings.idp.delete.success'))
      },
      onError: (error) => {
        if (handleIdpChallenge(error)) {
          return
        }
        if (isStepUpLocked(error)) {
          toasts.error(t('settings.security.stepUp.tooManyAttempts'))
          return
        }
        if (isStepUpFailed(error)) {
          toasts.error(t('settings.security.linked.invalidCredentials'))
          return
        }
        if (isStaleWrite(error)) {
          isDeleteOpen.value = false
        }
        toasts.error(isStaleWrite(error) ? t('app.staleError') : t('settings.idp.delete.error'))
      },
    },
  )
}

// Inline enable/disable. It is an edit of the provider, so it needs the administrator's step-up too.
// Tracks the row in flight so its switch shows as busy.
const togglingId = ref<number | null>(null)
const toggleTarget = ref<{ provider: IdentityProvider; enabled: boolean } | null>(null)
const isToggleStepUpOpen = ref(false)
const toggleReauth = ref<IdpReauth | null>(null)

/**
 * Asks for the administrator's step-up before flipping a provider's enabled state.
 *
 * @param provider - The provider being toggled.
 * @param enabled - The desired enabled state.
 */
function onToggle(provider: IdentityProvider, enabled: boolean): void {
  toggleTarget.value = { provider, enabled }
  isToggleStepUpOpen.value = true
}

/**
 * Flips the provider's enabled state by re-sending the full record with the step-up. The list
 * refetches on settle, so the switch reflects the server-authoritative value.
 *
 * @param stepUp - The administrator's step-up from the dialog.
 */
function confirmToggle(stepUp: StepUpInput): void {
  const target = toggleTarget.value
  if (!target) {
    return
  }
  const { provider, enabled } = target
  togglingId.value = provider.id
  updateMutation.mutate(
    {
      id: provider.id,
      input: { ...toProviderInput(provider), enabled },
      version: provider.version,
      stepUp,
    },
    {
      onSuccess: () => {
        isToggleStepUpOpen.value = false
        toasts.success(enabled ? t('settings.idp.enableSuccess') : t('settings.idp.disableSuccess'))
      },
      onError: (error) => {
        if (handleIdpChallenge(error)) {
          return
        }
        if (isStepUpLocked(error)) {
          toasts.error(t('settings.security.stepUp.tooManyAttempts'))
          return
        }
        if (isStepUpFailed(error)) {
          toasts.error(t('settings.security.linked.invalidCredentials'))
          return
        }
        isToggleStepUpOpen.value = false
        toasts.error(
          t(
            error instanceof HttpError && error.status === 412
              ? 'settings.idp.form.staleError'
              : 'settings.idp.toggleError',
          ),
        )
      },
      onSettled: () => {
        togglingId.value = null
      },
    },
  )
}

// The provider the returning sign-in was for is found in the list once it has loaded; the form dialog
// opens itself for an edit, and the toggle dialog is reopened here.
let resumeHandled = false
watch(
  providers,
  (list) => {
    const idpId = resumeTargetId(resume, ['admin_idp_edit', 'admin_idp_delete'], 'idpId')
    const provider = list.find((entry) => entry.id === idpId)
    if (resumeHandled || !resume || !provider) {
      return
    }
    resumeHandled = true
    if (resume.action === 'admin_idp_delete') {
      providerToDelete.value = provider
      deleteReauth.value = resume.reauth
      isDeleteOpen.value = true
    } else if (resume.pending.variant === 'toggle') {
      toggleTarget.value = { provider, enabled: resume.pending.enabled === true }
      toggleReauth.value = resume.reauth
      isToggleStepUpOpen.value = true
    } else {
      providerToEdit.value = provider
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-col gap-1">
        <h1 class="text-page-title">{{ t('settings.idp.title') }}</h1>
        <p class="text-body">{{ t('settings.idp.subtitle') }}</p>
      </div>
      <Button class="w-full sm:w-auto" @click="openAdd">
        <Plus class="size-4" aria-hidden="true" />
        {{ t('settings.idp.buttonAdd') }}
      </Button>
    </div>

    <ListPanel
      :is-loading="providersQuery.isPending.value"
      :is-error="providersQuery.isError.value"
      :is-empty="isEmpty"
      :show-header="false"
      :error-title="t('settings.idp.error.title')"
      :error-description="t('settings.idp.error.description')"
      :retry-label="t('settings.idp.error.retry')"
      @retry="providersQuery.refetch()"
    >
      <template #empty>
        <EmptyState
          :title="t('settings.idp.empty.title')"
          :description="t('settings.idp.empty.description')"
        >
          <template #icon>
            <KeyRound class="size-8" aria-hidden="true" />
          </template>
          <template #action>
            <Button @click="openAdd">
              <Plus class="size-4" aria-hidden="true" />
              {{ t('settings.idp.buttonAdd') }}
            </Button>
          </template>
        </EmptyState>
      </template>

      <ul class="divide-y divide-border">
        <li v-for="provider in providers" :key="provider.id">
          <IdentityProviderListItem
            :provider="provider"
            :toggle-pending="togglingId === provider.id"
            @edit="openEdit"
            @delete="openDelete"
            @toggle="onToggle"
          />
        </li>
      </ul>
    </ListPanel>

    <IdentityProviderFormDialog
      v-model:open="isFormOpen"
      :provider="providerToEdit"
      :templates="templates"
      :resume="resume"
      @success="(message) => toasts.success(message)"
      @error="(message) => toasts.error(message)"
    />

    <StepUpDialog
      v-if="toggleTarget"
      v-model:open="isToggleStepUpOpen"
      v-model:reauth="toggleReauth"
      action="admin_idp_edit"
      :title="t('settings.idp.form.stepUpTitle')"
      :description="t('settings.idp.toggleStepUpDescription', { name: toggleTarget.provider.name })"
      :confirm-label="t('settings.idp.toggleStepUpConfirm')"
      :require-password="requirePassword"
      :require-mfa="requireMfa"
      :pending-context="{
        variant: 'toggle',
        idpId: toggleTarget.provider.id,
        enabled: toggleTarget.enabled,
      }"
      :pending="updateMutation.isPending.value"
      @confirm="confirmToggle"
    />

    <StepUpDialog
      v-if="providerToDelete"
      v-model:open="isDeleteOpen"
      v-model:reauth="deleteReauth"
      action="admin_idp_delete"
      :title="t('settings.idp.delete.title')"
      :description="t('settings.idp.delete.body', { name: providerToDelete.name })"
      :confirm-label="t('settings.idp.delete.confirm')"
      :require-password="requirePassword"
      :require-mfa="requireMfa"
      :pending-context="{ idpId: providerToDelete.id }"
      destructive
      :pending="deleteMutation.isPending.value"
      @confirm="confirmDelete"
    />
  </div>
</template>
