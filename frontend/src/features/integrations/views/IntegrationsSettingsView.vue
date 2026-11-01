<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import GarminCard from '@/features/integrations/components/GarminCard.vue'
import StravaCard from '@/features/integrations/components/StravaCard.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { useProfileQuery } from '@/features/profile/composables/useProfile'

const { t } = useI18n()

// The self-profile carries the Strava/Garmin link flags that gate each card's
// connect-vs-options state; link/unlink mutations invalidate it.
const profileQuery = useProfileQuery()
const profile = computed(() => profileQuery.data.value ?? null)
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('settings.integrations.title') }}</h1>
      <p class="text-body">{{ t('settings.integrations.subtitle') }}</p>
    </div>

    <!-- Loading -->
    <div v-if="profileQuery.isPending.value" class="flex flex-col gap-3" aria-busy="true">
      <Card v-for="n in 2" :key="n" class="flex items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <Skeleton class="size-10 rounded-full" />
          <div class="flex flex-col gap-2">
            <Skeleton class="h-4 w-32" />
            <Skeleton class="h-3 w-48" />
          </div>
        </div>
        <Skeleton class="h-9 w-24" />
      </Card>
    </div>

    <!-- Error -->
    <ErrorState
      v-else-if="profileQuery.isError.value"
      :title="t('settings.integrations.loadError.title')"
      :description="t('settings.integrations.loadError.description')"
    >
      <template #action>
        <Button variant="outline" @click="() => profileQuery.refetch()">
          {{ t('settings.integrations.retry') }}
        </Button>
      </template>
    </ErrorState>

    <!-- Loaded -->
    <template v-else-if="profile">
      <StravaCard
        :linked="profile.stravaLinked"
        :integrations-version="profile.integrationsVersion"
      />
      <GarminCard :linked="profile.garminLinked" />
    </template>
  </div>
</template>
