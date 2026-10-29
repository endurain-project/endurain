<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ImageUp, Trash2 } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useToasts } from '@/composables/useToasts'
import {
  useDeleteLoginPhotoMutation,
  useUploadLoginPhotoMutation,
} from '@/features/serverSettings/composables/useServerSettings'
import { getApiBaseUrl } from '@/services/runtime'

const props = defineProps<{
  /** Whether a custom login photo is currently configured. */
  loginPhotoSet: boolean
}>()

const { t } = useI18n()
const toasts = useToasts()
const uploadMutation = useUploadLoginPhotoMutation()
const deleteMutation = useDeleteLoginPhotoMutation()

const fileInput = ref<HTMLInputElement | null>(null)
const isDeleteOpen = ref(false)
// Set to the stored photo's version after each upload so the browser refetches it instead of serving its
// cached copy.
const previewVersion = ref(Date.now())

const previewUrl = computed(
  () => `${getApiBaseUrl()}/public/server-settings/login-photo?v=${previewVersion.value}`,
)

/** Opens the native file picker. */
function pickFile(): void {
  fileInput.value?.click()
}

/**
 * Validates the chosen file is a PNG (the backend only accepts PNG for the
 * login image) and uploads it. The input is always reset so re-selecting the
 * same file fires `change` again.
 *
 * @param event - The file input change event.
 */
function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  if (file.type !== 'image/png' && !file.name.toLowerCase().endsWith('.png')) {
    toasts.error(t('settings.server.photo.invalidType'))
    return
  }
  uploadMutation.mutate(file, {
    onSuccess: (photo) => {
      previewVersion.value = photo.version
      toasts.success(t('settings.server.photo.uploadSuccess'))
    },
    onError: () => toasts.error(t('settings.server.photo.uploadError')),
  })
}

/** Removes the custom login photo after confirmation. */
function confirmDelete(): void {
  deleteMutation.mutate(undefined, {
    onSuccess: () => {
      isDeleteOpen.value = false
      toasts.success(t('settings.server.photo.deleteSuccess'))
    },
    onError: () => toasts.error(t('settings.server.photo.deleteError')),
  })
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-col gap-1">
      <h2 class="text-card-heading">{{ t('settings.server.photo.title') }}</h2>
      <p class="text-body">{{ t('settings.server.photo.description') }}</p>
    </div>

    <!-- Mirrors the photo column of AuthScreenLayout: square crop, scrim and taglines. -->
    <div
      v-if="props.loginPhotoSet"
      class="relative aspect-square w-full max-w-xs overflow-hidden rounded-input"
    >
      <img
        :src="previewUrl"
        :alt="t('settings.server.photo.previewAlt')"
        class="size-full object-cover"
      />
      <div
        class="absolute inset-0 bg-gradient-to-b from-black/40 via-transparent to-black/75"
      ></div>
      <div class="absolute inset-x-0 bottom-0 p-4 text-body leading-snug text-white">
        <p>{{ t('login.tagline1') }}</p>
        <p>{{ t('login.tagline2') }}</p>
      </div>
    </div>

    <input
      ref="fileInput"
      type="file"
      accept=".png,image/png"
      class="sr-only"
      @change="onFileChange"
    />

    <div class="flex flex-col gap-3 sm:flex-row">
      <Button
        type="button"
        variant="outline"
        class="w-full sm:w-auto"
        :disabled="uploadMutation.isPending.value"
        @click="pickFile"
      >
        <ImageUp class="size-4" aria-hidden="true" />
        {{ loginPhotoSet ? t('settings.server.photo.replace') : t('settings.server.photo.add') }}
      </Button>

      <Button
        v-if="loginPhotoSet"
        type="button"
        variant="outlineDestructive"
        class="w-full sm:w-auto"
        :disabled="deleteMutation.isPending.value"
        @click="isDeleteOpen = true"
      >
        <Trash2 class="size-4" aria-hidden="true" />
        {{ t('settings.server.photo.delete') }}
      </Button>
    </div>

    <ConfirmDialog
      v-model:open="isDeleteOpen"
      :title="t('settings.server.photo.deleteTitle')"
      :description="t('settings.server.photo.deleteConfirm')"
      :confirm-label="t('settings.server.photo.delete')"
      :cancel-label="t('settings.server.photo.cancel')"
      :close-label="t('settings.server.photo.close')"
      :pending="deleteMutation.isPending.value"
      @confirm="confirmDelete"
    />
  </Card>
</template>
