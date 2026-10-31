<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import BulkImportCard from '@/features/import/components/BulkImportCard.vue'
import GarminImportCard from '@/features/import/components/GarminImportCard.vue'
import StravaImportCard from '@/features/import/components/StravaImportCard.vue'

const { t } = useI18n()
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('settings.import.title') }}</h1>
      <p class="text-body">{{ t('settings.import.subtitle') }}</p>
    </div>

    <StravaImportCard />
    <GarminImportCard />
    <BulkImportCard />
  </div>
</template>
