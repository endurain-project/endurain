<script setup lang="ts">
import { RotateCw, TriangleAlert } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import LocaleSwitcher from '@/components/LocaleSwitcher.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import { Button } from '@/components/ui/button'

const { t } = useI18n()

// A full reload re-runs bootstrap, which asks the server about the session again.
function reloadPage(): void {
  window.location.reload()
}
</script>

<template>
  <div
    class="flex min-h-svh flex-col items-center justify-center bg-background p-4 text-foreground"
  >
    <div class="w-full max-w-xl rounded-card border border-border bg-card p-6 text-center sm:p-8">
      <div
        class="mb-6 flex flex-wrap items-center justify-center gap-3 border-b border-border pb-5"
      >
        <LocaleSwitcher />
        <ThemeToggle />
      </div>
      <div role="alert">
        <div class="mb-4 flex justify-center text-destructive">
          <TriangleAlert class="size-10" aria-hidden="true" />
        </div>
        <h1 class="mb-3 text-section-heading">{{ t('app.error.title') }}</h1>
        <p class="text-body">{{ t('app.sessionRestoreError') }}</p>
      </div>

      <Button class="mt-5" @click="reloadPage">
        <RotateCw class="size-4" aria-hidden="true" />
        {{ t('app.error.retry') }}
      </Button>
    </div>
  </div>
</template>
