<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import { Button } from '@/components/ui/button'

defineProps<{
  /** Whether a save is in flight; disables both actions and shows a spinner. */
  saving: boolean
  /** Whether the edits are valid enough to save. */
  canSave: boolean
}>()

defineEmits<{
  /** The user asked to save the edits. */
  save: []
  /** The user asked to drop the edits. */
  discard: []
}>()

const { t } = useI18n()
</script>

<template>
  <div
    role="region"
    :aria-label="t('settings.server.unsaved')"
    class="sticky bottom-[calc(5rem+env(safe-area-inset-bottom))] z-10 lg:bottom-3 flex flex-col gap-2 rounded-input border border-border bg-card p-3 shadow-md sm:flex-row sm:items-center sm:justify-between"
  >
    <p class="text-item-title">{{ t('settings.server.unsaved') }}</p>
    <div class="flex flex-col gap-2 sm:flex-row">
      <Button type="button" variant="ghost" :disabled="saving" @click="$emit('discard')">
        {{ t('settings.server.discard') }}
      </Button>
      <Button type="button" :disabled="!canSave || saving" @click="$emit('save')">
        <LoaderCircle v-if="saving" class="size-4 animate-spin" aria-hidden="true" />
        {{ saving ? t('settings.server.saving') : t('settings.server.save') }}
      </Button>
    </div>
  </div>
</template>
