<template>
  <div class="my-1">
    <div class="d-flex justify-content-between align-items-center mb-1">
      <label :for="inputId" class="form-label mb-0">
        <b v-if="required">* {{ label }}</b>
        <b v-else>{{ label }}</b>
      </label>
      <button
        type="button"
        class="btn btn-sm btn-outline-secondary"
        @click="togglePreview"
        :aria-label="showPreview ? hidePreviewLabel : showPreviewLabel"
      >
        <font-awesome-icon v-if="showPreview" :icon="['fas', 'edit']" />
        <font-awesome-icon v-else :icon="['fas', 'eye']" />
        <span class="ms-1">{{ showPreview ? hidePreviewLabel : showPreviewLabel }}</span>
      </button>
    </div>

    <div v-if="!showPreview">
      <textarea
        :id="inputId"
        class="form-control"
        :name="inputId"
        :placeholder="placeholder"
        :maxlength="maxlength"
        :rows="rows"
        :required="required"
        :aria-describedby="`${inputId}-help`"
        v-model="internalValue"
      ></textarea>
      <small :id="`${inputId}-help`" class="form-text text-muted">
        {{ markdownHelpText }}
      </small>
    </div>

    <div v-else class="markdown-preview border rounded p-2 bg-body-tertiary overflow-auto">
      <MarkdownContentComponent :content="internalValue" :aria-label="`${label} preview`" />
      <p v-if="!internalValue" class="text-muted mb-0">
        {{ emptyPreviewText }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import MarkdownContentComponent from '@/components/GeneralComponents/MarkdownContentComponent.vue'

/**
 * Props for the MarkdownEditorComponent.
 *
 * @property modelValue - The v-model bound value (can be null/undefined).
 * @property label - Label text for the input.
 * @property placeholder - Placeholder text.
 * @property maxlength - Maximum character length.
 * @property rows - Number of textarea rows.
 * @property required - Whether the field is required.
 * @property inputId - Unique ID for the input element.
 */
interface Props {
  modelValue?: string | null
  label: string
  placeholder?: string
  maxlength?: number
  rows?: number
  required?: boolean
  inputId: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  placeholder: '',
  maxlength: 2500,
  rows: 4,
  required: false
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | null): void
}>()

const { t } = useI18n()

const showPreview = ref(false)

/**
 * Computed property for two-way binding with parent component.
 * Handles null values gracefully.
 */
const internalValue = computed({
  get: () => props.modelValue ?? '',
  set: (value: string) => emit('update:modelValue', value || null)
})

/**
 * Toggle between edit and preview modes.
 */
const togglePreview = () => {
  showPreview.value = !showPreview.value
}

/**
 * Localized text for the show preview button.
 */
const showPreviewLabel = computed(() => t('generalItems.markdownEditor.showPreview'))

/**
 * Localized text for the hide preview button.
 */
const hidePreviewLabel = computed(() => t('generalItems.markdownEditor.hidePreview'))

/**
 * Localized help text for markdown formatting.
 */
const markdownHelpText = computed(() => t('generalItems.markdownEditor.markdownSupported'))

/**
 * Localized text for empty preview state.
 */
const emptyPreviewText = computed(() => t('generalItems.markdownEditor.noContentToPreview'))
</script>

<style scoped>
.markdown-preview {
  min-height: 100px;
  max-height: 300px;
}
</style>
