<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { EllipsisVertical, ImagePlus, Pencil, Trash2 } from '@lucide/vue'

import type { Activity } from '@/features/activities/types'

import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useToasts } from '@/composables/useToasts'
import {
  useDeleteActivityMutation,
  useUploadActivityMediaMutation,
} from '@/features/activities/composables/useActivityDetail'
import ActivityEditDialog from '@/features/activities/components/ActivityEditDialog.vue'

const props = defineProps<{
  /** The activity these owner-only actions apply to. */
  activity: Activity
}>()

const { t } = useI18n()
const router = useRouter()
const toasts = useToasts()

const deleteMutation = useDeleteActivityMutation()
const uploadMutation = useUploadActivityMediaMutation(() => props.activity.id)
const isDeleteOpen = ref(false)
const isEditOpen = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

/** Opens the native file picker for the Add photo action. */
function openFilePicker(): void {
  fileInput.value?.click()
}

/** Uploads the chosen image, resetting the input so the same file re-selects. */
async function onFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  input.value = ''
  if (!file) {
    return
  }
  if (!file.type.startsWith('image/')) {
    toasts.error(t('activities.media.invalidType'))
    return
  }
  try {
    await uploadMutation.mutateAsync(file)
    toasts.success(t('activities.media.uploadSuccess'))
  } catch {
    toasts.error(t('activities.media.uploadError'))
  }
}

/** Deletes the activity, then returns to the home feed. */
async function confirmDelete(): Promise<void> {
  try {
    await deleteMutation.mutateAsync({
      id: props.activity.id,
      version: props.activity.version,
    })
    isDeleteOpen.value = false
    toasts.success(t('activities.actions.deleteSuccess'))
    await router.push({ name: 'home' })
  } catch {
    toasts.error(t('activities.actions.deleteError'))
  }
}
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger
      class="flex cursor-pointer items-center rounded-input p-1 text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/30"
      :aria-label="t('activities.actions.menu')"
    >
      <EllipsisVertical class="size-5" />
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end">
      <DropdownMenuItem @select="openFilePicker">
        <ImagePlus class="size-4" />
        <span>{{ t('activities.media.addMedia') }}</span>
      </DropdownMenuItem>
      <DropdownMenuItem @select="isEditOpen = true">
        <Pencil class="size-4" />
        <span>{{ t('activities.actions.edit') }}</span>
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem
        class="text-destructive hover:bg-destructive/10 hover:text-destructive focus:bg-destructive/10 focus:text-destructive data-[highlighted]:bg-destructive/10 data-[highlighted]:text-destructive"
        @select="isDeleteOpen = true"
      >
        <Trash2 class="size-4" />
        <span>{{ t('activities.actions.delete') }}</span>
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>

  <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onFileSelected" />

  <ActivityEditDialog v-model:open="isEditOpen" :activity="activity" />

  <ConfirmDialog
    v-model:open="isDeleteOpen"
    :title="t('activities.actions.deleteTitle')"
    :description="t('activities.actions.deleteBody', { name: activity.name })"
    :confirm-label="t('activities.actions.delete')"
    :cancel-label="t('activities.actions.cancel')"
    :close-label="t('activities.actions.close')"
    :pending="deleteMutation.isPending.value"
    @confirm="confirmDelete"
  />
</template>
