<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ImageUp, Trash2, UserPen } from '@lucide/vue'

import type { ProfileDetails } from '@/features/profile/types'

import ProfileFormDialog from '@/features/profile/components/ProfileFormDialog.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useToasts } from '@/composables/useToasts'
import { cmToFeetInches } from '@/utils/units'
import {
  useDeleteProfilePhotoMutation,
  useUploadProfilePhotoMutation,
} from '@/features/profile/composables/useProfile'

const props = defineProps<{
  /** The current user's profile. */
  profile: ProfileDetails
}>()

const { t } = useI18n()
const toasts = useToasts()
const uploadMutation = useUploadProfilePhotoMutation()
const deleteMutation = useDeleteProfilePhotoMutation()

const fileInput = ref<HTMLInputElement | null>(null)
const isEditOpen = ref(false)
const isDeletePhotoOpen = ref(false)

/** Formatted height respecting the user's unit system, or `null` when unset. */
const heightDisplay = computed<string | null>(() => {
  if (props.profile.height === null) {
    return null
  }
  if (props.profile.units === 'metric') {
    return `${props.profile.height} ${t('settings.users.form.unitCm')}`
  }
  const { feet, inches } = cmToFeetInches(props.profile.height)
  return `${feet}' ${inches}"`
})

/** The read-only profile fields, in display order, pre-formatted. */
const fields = computed<{ label: string; value: string | null }[]>(() => [
  { label: t('settings.users.form.email'), value: props.profile.email },
  { label: t('settings.users.form.city'), value: props.profile.city },
  { label: t('settings.users.form.birthdate'), value: props.profile.birthdate },
  {
    label: t('settings.users.form.gender'),
    value: t(`settings.users.form.genders.${props.profile.gender}`),
  },
  {
    label: t('settings.users.form.units'),
    value:
      props.profile.units === 'metric'
        ? t('settings.users.form.unitsMetric')
        : t('settings.users.form.unitsImperial'),
  },
  // Weight units follow the units setting above unless an override is set.
  {
    label: t('settings.users.form.weightUnits'),
    value: t(
      (props.profile.weightUnits ?? props.profile.units) === 'imperial'
        ? 'settings.users.form.weightUnitsImperial'
        : 'settings.users.form.weightUnitsMetric',
    ),
  },
  {
    label: t('settings.users.form.currency'),
    value: t(`settings.users.form.currencies.${props.profile.currency}`),
  },
  { label: t('settings.users.form.height'), value: heightDisplay.value },
  {
    label: t('settings.users.form.maxHeartRate'),
    value: props.profile.maxHeartRate
      ? `${props.profile.maxHeartRate} ${t('settings.users.form.unitBpm')}`
      : null,
  },
  {
    label: t('settings.users.form.preferredLanguage'),
    value: t(`settings.users.form.languages.${props.profile.preferredLanguage}`),
  },
  {
    label: t('settings.users.form.firstDayOfWeek'),
    value: t(`settings.users.form.weekdays.${props.profile.firstDayOfWeek}`),
  },
  {
    label: t('settings.users.form.accessType'),
    value:
      props.profile.accessType === 'admin'
        ? t('settings.users.form.accessTypeAdmin')
        : t('settings.users.form.accessTypeRegular'),
  },
])

/** Opens the native file picker. */
function pickPhoto(): void {
  fileInput.value?.click()
}

/**
 * Validates the chosen file is an image and uploads it as the new profile
 * photo. The input is always reset so re-selecting the same file fires again.
 *
 * @param event - The file input change event.
 */
function onPhotoChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  if (!file.type.startsWith('image/')) {
    toasts.error(t('settings.profile.photo.invalidType'))
    return
  }
  uploadMutation.mutate(file, {
    onSuccess: () => toasts.success(t('settings.profile.photo.uploadSuccess')),
    onError: () => toasts.error(t('settings.profile.photo.uploadError')),
  })
}

/** Removes the current profile photo after confirmation. */
function confirmDeletePhoto(): void {
  deleteMutation.mutate(undefined, {
    onSuccess: () => {
      isDeletePhotoOpen.value = false
      toasts.success(t('settings.profile.photo.deleteSuccess'))
    },
    onError: () => toasts.error(t('settings.profile.photo.deleteError')),
  })
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start">
      <div class="flex flex-col items-center gap-3">
        <UserAvatar
          :src="profile.avatarUrl"
          :alt="profile.name"
          size-class="size-28"
          icon-class="size-12"
        />
        <div class="text-center">
          <p class="font-medium text-foreground">{{ profile.name }}</p>
          <p class="text-hint">@{{ profile.username }}</p>
        </div>
      </div>

      <dl class="flex-1 grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        <div v-for="field in fields" :key="field.label" class="flex flex-col">
          <dt class="text-caption">{{ field.label }}</dt>
          <dd class="text-body text-foreground">
            {{ field.value ?? t('settings.profile.notSet') }}
          </dd>
        </div>
      </dl>
    </div>

    <input ref="fileInput" type="file" accept="image/*" class="sr-only" @change="onPhotoChange" />

    <div class="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
      <Button class="w-full sm:w-auto" @click="isEditOpen = true">
        <UserPen class="size-4" aria-hidden="true" />
        {{ t('settings.profile.edit.button') }}
      </Button>
      <Button
        variant="outline"
        class="w-full sm:w-auto"
        :disabled="uploadMutation.isPending.value"
        @click="pickPhoto"
      >
        <ImageUp class="size-4" aria-hidden="true" />
        {{
          profile.photoPath ? t('settings.profile.photo.replace') : t('settings.profile.photo.add')
        }}
      </Button>
      <Button
        v-if="profile.photoPath"
        variant="outlineDestructive"
        class="w-full sm:w-auto"
        :disabled="deleteMutation.isPending.value"
        @click="isDeletePhotoOpen = true"
      >
        <Trash2 class="size-4" aria-hidden="true" />
        {{ t('settings.profile.photo.delete') }}
      </Button>
    </div>

    <ProfileFormDialog
      v-model:open="isEditOpen"
      :profile="profile"
      @success="(message) => toasts.success(message)"
      @error="(message) => toasts.error(message)"
    />

    <ConfirmDialog
      v-model:open="isDeletePhotoOpen"
      :title="t('settings.profile.photo.deleteTitle')"
      :description="t('settings.profile.photo.deleteConfirm')"
      :confirm-label="t('settings.profile.photo.delete')"
      :cancel-label="t('settings.profile.photo.cancel')"
      :close-label="t('settings.profile.photo.close')"
      :pending="deleteMutation.isPending.value"
      @confirm="confirmDeletePhoto"
    />
  </Card>
</template>
