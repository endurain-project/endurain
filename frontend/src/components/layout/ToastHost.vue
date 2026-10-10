<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { X } from '@lucide/vue'

import { useToasts } from '@/composables/useToasts'
import { severityToastClasses } from '@/lib/severity'

defineProps<{
  /** Offset toasts below the app navbar (set when the chrome/navbar is shown). */
  belowNavbar?: boolean
}>()

const { t } = useI18n()
const { toasts, dismiss } = useToasts()
</script>

<template>
  <TransitionGroup
    tag="div"
    class="pointer-events-none fixed inset-x-0 z-[60] flex flex-col items-center gap-2 px-4"
    :class="belowNavbar ? 'top-safe-nav' : 'top-3'"
    enter-active-class="transition-opacity duration-300 ease-out"
    enter-from-class="opacity-0"
    enter-to-class="opacity-100"
    leave-active-class="transition-opacity duration-300 ease-in"
    leave-from-class="opacity-100"
    leave-to-class="opacity-0"
    move-class="transition-transform duration-300 ease-out"
  >
    <div
      v-for="toast in toasts"
      :key="toast.id"
      class="pointer-events-auto flex w-full max-w-sm items-start gap-2 rounded-input border px-3 py-2 text-meta shadow-lg"
      :class="severityToastClasses[toast.kind]"
      role="status"
      aria-live="polite"
    >
      <span class="flex-1">{{ toast.message }}</span>
      <button
        type="button"
        class="inline-flex size-5 shrink-0 items-center justify-center rounded-input opacity-70 transition-opacity hover:opacity-100 focus:outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
        :aria-label="t('app.dismiss')"
        @click="dismiss(toast.id)"
      >
        <X class="size-3.5" />
      </button>
    </div>
  </TransitionGroup>
</template>
