<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Eye, EyeOff } from '@lucide/vue'

import { Input } from '@/components/ui/input'

const model = defineModel<string>({ required: true })

withDefaults(
  defineProps<{
    /** Field id, associated with an external `<Label>`. */
    id?: string
    /** Form field name, used by password managers/autofill. */
    name?: string
    /** Autocomplete hint (e.g. `current-password`, `new-password`). */
    autocomplete?: string
    /** Placeholder text. */
    placeholder?: string
    /** Maximum allowed character length. */
    maxlength?: number
    /** Whether the field is disabled. */
    disabled?: boolean
    /** Marks the field invalid for assistive tech. */
    ariaInvalid?: boolean
    /** Id of the element describing the field (e.g. an error message). */
    ariaDescribedby?: string
  }>(),
  {
    id: undefined,
    name: undefined,
    autocomplete: 'off',
    placeholder: undefined,
    maxlength: undefined,
    disabled: false,
    ariaInvalid: false,
    ariaDescribedby: undefined,
  },
)

const emit = defineEmits<{
  /** The input lost focus; forwarded so a form can validate the field on blur. */
  blur: [event: FocusEvent]
}>()

const { t } = useI18n()

/** Whether the value is currently revealed as plain text. */
const show = ref(false)
</script>

<template>
  <div class="relative">
    <Input
      :id="id"
      v-model="model"
      :name="name"
      :type="show ? 'text' : 'password'"
      :autocomplete="autocomplete"
      :placeholder="placeholder"
      :maxlength="maxlength"
      :disabled="disabled"
      :aria-invalid="ariaInvalid"
      :aria-describedby="ariaDescribedby"
      class="w-full pr-10"
      @blur="emit('blur', $event)"
    />
    <button
      type="button"
      class="absolute right-1 top-1/2 inline-flex size-7 -translate-y-1/2 items-center justify-center rounded-input text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
      :aria-label="show ? t('settings.security.hidePassword') : t('settings.security.showPassword')"
      :disabled="disabled"
      tabindex="-1"
      @click="show = !show"
    >
      <EyeOff v-if="show" class="size-4" aria-hidden="true" />
      <Eye v-else class="size-4" aria-hidden="true" />
    </button>
  </div>
</template>
