<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { KeyRound, Plus } from '@lucide/vue'

import type { IdentityProvider } from '@/features/identityProviders/types'

import IdentityProviderFormDialog from '@/features/identityProviders/components/IdentityProviderFormDialog.vue'
import IdentityProviderListItem from '@/features/identityProviders/components/IdentityProviderListItem.vue'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { EmptyState } from '@/components/ui/empty-state'
import { ListPanel } from '@/components/ui/list-panel'
import { useToasts } from '@/composables/useToasts'
import { HttpError } from '@/services/http'
import { toProviderInput } from '@/features/identityProviders/services/identityProviders'
import {
  useDeleteIdentityProviderMutation,
  useIdentityProvidersQuery,
  useIdentityProviderTemplatesQuery,
  useUpdateIdentityProviderMutation,
} from '@/features/identityProviders/composables/useIdentityProviders'

const { t } = useI18n()
const toasts = useToasts()

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

// Delete confirmation state.
const isDeleteOpen = ref(false)
const providerToDelete = ref<IdentityProvider | null>(null)

/** Opens the delete confirmation for the given provider. */
function openDelete(provider: IdentityProvider): void {
  providerToDelete.value = provider
  isDeleteOpen.value = true
}

/** Deletes the pending provider; the backend blocks deletion of linked providers. */
function confirmDelete(): void {
  const provider = providerToDelete.value
  if (!provider) {
    return
  }
  deleteMutation.mutate(
    { id: provider.id, version: provider.version },
    {
      onSuccess: () => {
        isDeleteOpen.value = false
        toasts.success(t('settings.idp.delete.success'))
      },
      onError: () => toasts.error(t('settings.idp.delete.error')),
    },
  )
}

// Inline enable/disable. Tracks the row in flight so its switch shows as busy.
const togglingId = ref<number | null>(null)

/**
 * Flips a provider's enabled state by re-sending the full record. The list
 * refetches on settle, so the switch reflects the server-authoritative value.
 *
 * @param provider - The provider being toggled.
 * @param enabled - The desired enabled state.
 */
function onToggle(provider: IdentityProvider, enabled: boolean): void {
  togglingId.value = provider.id
  updateMutation.mutate(
    {
      id: provider.id,
      input: { ...toProviderInput(provider), enabled },
      version: provider.version,
    },
    {
      onSuccess: () => {
        toasts.success(enabled ? t('settings.idp.enableSuccess') : t('settings.idp.disableSuccess'))
      },
      onError: (error) =>
        toasts.error(
          t(
            error instanceof HttpError && error.status === 412
              ? 'settings.idp.form.staleError'
              : 'settings.idp.toggleError',
          ),
        ),
      onSettled: () => {
        togglingId.value = null
      },
    },
  )
}
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
      @success="(message) => toasts.success(message)"
      @error="(message) => toasts.error(message)"
    />

    <ConfirmDialog
      v-model:open="isDeleteOpen"
      :title="t('settings.idp.delete.title')"
      :description="t('settings.idp.delete.body', { name: providerToDelete?.name ?? '' })"
      :confirm-label="t('settings.idp.delete.confirm')"
      :cancel-label="t('settings.idp.delete.cancel')"
      :close-label="t('settings.idp.delete.close')"
      :pending="deleteMutation.isPending.value"
      @confirm="confirmDelete"
    />
  </div>
</template>
