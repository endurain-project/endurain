<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Pencil, Trash2 } from '@lucide/vue'

import type { IdentityProvider } from '@/features/identityProviders/types'

import ProviderLogo from '@/features/identityProviders/components/ProviderLogo.vue'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'

defineProps<{
  /** The provider to render. */
  provider: IdentityProvider
  /** Whether this row's enable/disable toggle is in flight. */
  togglePending?: boolean
}>()

const emit = defineEmits<{
  edit: [provider: IdentityProvider]
  delete: [provider: IdentityProvider]
  toggle: [provider: IdentityProvider, enabled: boolean]
}>()

const { t } = useI18n()

/** Human-readable label for the provider protocol. */
function providerTypeLabel(type: string): string {
  if (type === 'oidc') {
    return t('settings.idp.type.oidc')
  }
  if (type === 'oauth2') {
    return t('settings.idp.type.oauth2')
  }
  return type
}
</script>

<template>
  <div class="flex items-center gap-3 px-4 py-3">
    <ProviderLogo
      :icon="provider.icon"
      :name="provider.name"
      :slug="provider.slug"
      :icon-uploaded="provider.iconUploaded"
      :version="provider.version"
    />

    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <p class="truncate font-medium text-foreground">{{ provider.name }}</p>
        <Badge v-if="!provider.enabled" variant="destructive">
          {{ t('settings.idp.list.disabled') }}
        </Badge>
      </div>
      <p class="truncate text-hint">
        {{ providerTypeLabel(provider.providerType) }} · {{ provider.slug }}
      </p>
    </div>

    <div class="flex shrink-0 items-center gap-1">
      <Switch
        :model-value="provider.enabled"
        :disabled="togglePending"
        :aria-label="t('settings.idp.list.toggle', { name: provider.name })"
        class="mr-1"
        @update:model-value="(value) => emit('toggle', provider, value)"
      />
      <button
        type="button"
        class="inline-flex size-8 items-center justify-center rounded-input text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
        :aria-label="t('settings.idp.list.edit', { name: provider.name })"
        @click="emit('edit', provider)"
      >
        <Pencil class="size-4" aria-hidden="true" />
      </button>
      <button
        type="button"
        class="inline-flex size-8 items-center justify-center rounded-input text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-destructive/30"
        :aria-label="t('settings.idp.list.delete', { name: provider.name })"
        @click="emit('delete', provider)"
      >
        <Trash2 class="size-4" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>
