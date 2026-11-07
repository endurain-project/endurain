<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ban, ImageUp } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import {
  BUILTIN_PROVIDER_ICONS,
  ICON_ACCEPTED_TYPES,
  UPLOADED_ICON,
  resolveProviderLogo,
} from '@/features/identityProviders/utils/providerIcon'

/** Display labels for the built-in provider icons (proper nouns, not translated). */
const ICON_LABELS: Record<string, string> = {
  authelia: 'Authelia',
  authentik: 'Authentik',
  casdoor: 'Casdoor',
  keycloak: 'Keycloak',
  pocketid: 'Pocket ID',
}

const props = defineProps<{
  /** The chosen icon source: `''` (none), a built-in key, or the upload sentinel. */
  modelValue: string
  /** The image picked for upload, or `null` when none is picked. */
  file: File | null
  /** Where the provider's already-stored uploaded image is served, or `null` when it has none. */
  storedSrc: string | null
  /** Why the picked image is unusable, or `null`. */
  error: string | null
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  /** The user picked an image, or cleared the picker. */
  pick: [file: File | null]
}>()

const { t } = useI18n()

const fileInput = ref<HTMLInputElement | null>(null)

const isUpload = computed(() => props.modelValue === UPLOADED_ICON)

// The preview shows the picked image until it is saved, then the stored one. It is read as a data URL:
// the page's Content-Security-Policy allows `data:` images but not `blob:` ones.
const pickedSrc = ref<string | null>(null)
watch(
  () => props.file,
  (file) => {
    pickedSrc.value = null
    if (!file) {
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      // A newer pick replaces this one before it finishes reading.
      if (props.file === file && typeof reader.result === 'string') {
        pickedSrc.value = reader.result
      }
    }
    reader.readAsDataURL(file)
  },
  { immediate: true },
)
const previewSrc = computed(() => pickedSrc.value ?? props.storedSrc)

// Prompt for a missing image only once the upload option has been chosen.
const missing = computed(() => isUpload.value && !props.file && !props.storedSrc)

/** Opens the native file picker. */
function chooseFile(): void {
  fileInput.value?.click()
}

/**
 * Hands the picked file to the form. The input is always reset so choosing the
 * same file again fires `change`.
 *
 * @param event - The file input change event.
 */
function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  input.value = ''
  emit('pick', file)
}

/** The selectable sources, in display order. */
const options = computed(() => [
  { value: '', label: t('settings.idp.form.iconNone') },
  ...BUILTIN_PROVIDER_ICONS.map((key) => ({ value: key, label: ICON_LABELS[key] ?? key })),
  { value: UPLOADED_ICON, label: t('settings.idp.form.iconUpload') },
])
</script>

<template>
  <div class="flex flex-col gap-2 sm:col-span-2">
    <Label id="provider-icon-label">{{ t('settings.idp.form.icon') }}</Label>

    <div
      role="radiogroup"
      aria-labelledby="provider-icon-label"
      class="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-7"
    >
      <button
        v-for="option in options"
        :key="option.value"
        type="button"
        role="radio"
        :aria-checked="modelValue === option.value"
        :disabled="disabled"
        :class="
          cn(
            'flex flex-col items-center gap-1.5 rounded-input border border-border px-2 py-3 text-hint transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50',
            modelValue === option.value && 'border-primary bg-primary/10 text-foreground',
          )
        "
        @click="emit('update:modelValue', option.value)"
      >
        <ImageUp v-if="option.value === UPLOADED_ICON" class="size-6" aria-hidden="true" />
        <Ban v-else-if="option.value === ''" class="size-6" aria-hidden="true" />
        <img
          v-else
          :src="resolveProviderLogo(option.value) ?? undefined"
          alt=""
          class="size-6 object-contain"
        />
        <span class="text-center leading-tight">{{ option.label }}</span>
      </button>
    </div>

    <div
      v-if="isUpload"
      class="flex flex-col gap-2 rounded-input border border-dashed border-border p-3"
    >
      <div class="flex items-center gap-3">
        <div
          class="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-input bg-muted-foreground/15"
        >
          <img
            v-if="previewSrc"
            :src="previewSrc"
            :alt="t('settings.idp.form.iconPreviewAlt')"
            class="size-full object-contain p-1"
          />
          <ImageUp v-else class="size-5 text-muted-foreground" aria-hidden="true" />
        </div>
        <div class="flex min-w-0 flex-1 flex-col gap-1">
          <Button
            type="button"
            variant="outline"
            size="sm"
            class="w-full sm:w-auto sm:self-start"
            :disabled="disabled"
            @click="chooseFile"
          >
            {{
              previewSrc ? t('settings.idp.form.iconReplace') : t('settings.idp.form.iconChoose')
            }}
          </Button>
          <p v-if="file" class="truncate text-hint">{{ file.name }}</p>
        </div>
      </div>
      <input
        ref="fileInput"
        type="file"
        name="iconFile"
        :accept="ICON_ACCEPTED_TYPES.join(',')"
        class="sr-only"
        tabindex="-1"
        @change="onFileChange"
      />
      <p v-if="error" class="text-field-error" role="alert">{{ error }}</p>
      <p v-else-if="missing" class="text-field-error" role="alert">
        {{ t('settings.idp.form.iconFileRequired') }}
      </p>
      <p v-else class="text-hint">{{ t('settings.idp.form.iconFileHint') }}</p>
    </div>
  </div>
</template>
