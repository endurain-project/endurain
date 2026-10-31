<script setup lang="ts">
import { LoaderCircle } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

/**
 * Modal-dialog shell for an edit form: the `Dialog`/`<form>`/header/footer
 * chrome plus the cancel and submit buttons, so each feature form supplies only
 * its fields (the default slot) and its labels. Presentational and
 * i18n-agnostic — every label is a prop. Pair the default slot with `useForm`
 * and `FormField`; wire `@submit` to the form's `handleSubmit`.
 */
const open = defineModel<boolean>('open', { required: true })

withDefaults(
  defineProps<{
    /** Dialog heading. */
    title: string
    /** Optional supporting copy below the title. */
    description?: string
    /** Label for the submit button (e.g. "Add gear" / "Save changes"). */
    submitLabel: string
    /** Label for the cancel button. */
    cancelLabel: string
    /** Accessible label for the built-in close (X) button. */
    closeLabel: string
    /** Whether a submit is in flight; disables controls and shows a spinner. */
    submitting?: boolean
    /** Whether the form is currently valid; gates the submit button. */
    canSubmit?: boolean
    /** Extra classes for the dialog surface (e.g. a wider `max-w-*`). */
    contentClass?: string
    /** Whether the submit action is destructive (renders the submit button in the destructive style). */
    destructive?: boolean
  }>(),
  { submitting: false, canSubmit: true, contentClass: undefined, destructive: false },
)

const emit = defineEmits<{
  /** The form was submitted (validation is the caller's responsibility). */
  submit: []
}>()
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent :close-label="closeLabel" :class="contentClass">
      <form novalidate @submit.prevent="emit('submit')">
        <DialogHeader>
          <DialogTitle>{{ title }}</DialogTitle>
          <DialogDescription v-if="description">{{ description }}</DialogDescription>
        </DialogHeader>

        <div class="mt-4 max-h-[70vh] overflow-y-auto px-0.5">
          <slot />
        </div>

        <DialogFooter class="mt-3">
          <Button type="button" variant="ghost" :disabled="submitting" @click="open = false">
            {{ cancelLabel }}
          </Button>
          <Button
            type="submit"
            :variant="destructive ? 'destructive' : 'default'"
            :disabled="submitting || !canSubmit"
          >
            <LoaderCircle v-if="submitting" class="size-4 animate-spin" aria-hidden="true" />
            <span>{{ submitLabel }}</span>
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
