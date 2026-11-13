<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import ServerSettingsForm from '@/features/serverSettings/components/ServerSettingsForm.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { useToasts } from '@/composables/useToasts'
import { consumeIdpStepUpReturn } from '@/features/security/composables/useIdpStepUp'
import {
  provideMailStepUpResume,
  provideSettingsStepUpResume,
} from '@/features/serverSettings/composables/useMailStepUpResume'
import {
  useServerSettingsQuery,
  useTileMapsTemplatesQuery,
} from '@/features/serverSettings/composables/useServerSettings'

const { t } = useI18n()
const toasts = useToasts()

// Returning from an identity-provider sign-in, the callback leaves its outcome in the URL fragment. It is
// consumed once; the mail form or the settings form reopens its step-up dialog, and a failure is reported once the page is shown.
const stepUpReturn = consumeIdpStepUpReturn()
const resume = stepUpReturn && !stepUpReturn.error ? stepUpReturn : null
provideMailStepUpResume(resume)
provideSettingsStepUpResume(resume)
onMounted(() => {
  if (stepUpReturn?.error === 'not_fresh') {
    toasts.error(t('settings.security.stepUp.notFresh'))
  } else if (stepUpReturn?.error) {
    toasts.error(t('settings.security.stepUp.failed'))
  }
})

const settingsQuery = useServerSettingsQuery()
const templatesQuery = useTileMapsTemplatesQuery()

// Wait for both the settings and the (static) presets so the maps section can
// match the saved URL to a preset on first render instead of flashing "custom".
const isLoading = computed(() => settingsQuery.isPending.value || templatesQuery.isPending.value)
const settings = computed(() => settingsQuery.data.value ?? null)
const templates = computed(() => templatesQuery.data.value ?? [])
</script>

<template>
  <div class="flex flex-col gap-3">
    <header class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('settings.server.title') }}</h1>
      <p class="text-body">{{ t('settings.server.subtitle') }}</p>
    </header>

    <div v-if="isLoading" class="flex flex-col gap-3" aria-busy="true">
      <Card v-for="section in 3" :key="section" class="flex flex-col gap-3">
        <Skeleton class="h-6 w-40" />
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Skeleton v-for="field in 3" :key="field" class="h-9 w-full" />
        </div>
      </Card>
    </div>

    <Card v-else-if="settingsQuery.isError.value" padding="none">
      <ErrorState
        :title="t('settings.server.loadError.title')"
        :description="t('settings.server.loadError.description')"
      >
        <template #action>
          <Button variant="outline" @click="settingsQuery.refetch()">
            {{ t('settings.server.loadError.retry') }}
          </Button>
        </template>
      </ErrorState>
    </Card>

    <template v-else-if="settings">
      <!-- Keyed on the version: a refetch that changes it rebuilds the form, so its If-Match is the one it shows. -->
      <ServerSettingsForm :key="settings.version" :settings="settings" :templates="templates" />
    </template>
  </div>
</template>
