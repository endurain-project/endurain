<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import DefaultGearForm from '@/features/profile/components/DefaultGearForm.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useDefaultGearQuery,
  useGearTypeOptionsQuery,
} from '@/features/profile/composables/useDefaultGear'

const { t } = useI18n()

const defaultGearQuery = useDefaultGearQuery()
const optionsQuery = useGearTypeOptionsQuery()

// Wait for both the assignments and the gear options so every selector can show
// its current value and choices on first render.
const isLoading = computed(() => defaultGearQuery.isPending.value || optionsQuery.isPending.value)
const isError = computed(() => defaultGearQuery.isError.value || optionsQuery.isError.value)
const defaultGear = computed(() => defaultGearQuery.data.value ?? null)
const options = computed(() => optionsQuery.data.value ?? {})

/** Refetches both backing queries after an error. */
function retry(): void {
  void defaultGearQuery.refetch()
  void optionsQuery.refetch()
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-col gap-1">
      <h2 class="text-card-heading">{{ t('settings.profile.defaultGear.title') }}</h2>
      <p class="text-body">{{ t('settings.profile.defaultGear.subtitle') }}</p>
    </div>

    <div
      v-if="isLoading"
      class="grid gap-x-6 gap-y-5 sm:grid-cols-2 lg:grid-cols-3"
      aria-busy="true"
    >
      <div v-for="section in 3" :key="section" class="flex flex-col gap-2">
        <Skeleton class="h-3 w-24" />
        <Skeleton v-for="row in 3" :key="row" class="h-9 w-full" />
      </div>
    </div>

    <ErrorState
      v-else-if="isError"
      :title="t('settings.profile.defaultGear.error.title')"
      :description="t('settings.profile.defaultGear.error.description')"
      @retry="retry"
    >
      <template #action="{ retry: onRetry }">
        <Button variant="outline" @click="onRetry">
          {{ t('settings.profile.defaultGear.error.retry') }}
        </Button>
      </template>
    </ErrorState>

    <!-- Keyed on the version: a refetch that changes it rebuilds the form, so its If-Match is the one it shows. -->
    <DefaultGearForm
      v-else-if="defaultGear"
      :key="defaultGear.version"
      :default-gear="defaultGear"
      :options="options"
    />

    <p v-else class="text-body">{{ t('settings.profile.defaultGear.unavailable') }}</p>
  </Card>
</template>
