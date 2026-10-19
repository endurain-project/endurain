<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import EmailCard from '@/features/serverSettings/components/EmailCard.vue'
import LoginPhotoCard from '@/features/serverSettings/components/LoginPhotoCard.vue'
import ServerSettingsForm from '@/features/serverSettings/components/ServerSettingsForm.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useServerSettingsQuery,
  useTileMapsTemplatesQuery,
} from '@/features/serverSettings/composables/useServerSettings'

const { t } = useI18n()

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
      <ServerSettingsForm :settings="settings" :templates="templates" />
      <LoginPhotoCard :login-photo-set="settings.loginPhotoSet" />
      <EmailCard />
    </template>
  </div>
</template>
