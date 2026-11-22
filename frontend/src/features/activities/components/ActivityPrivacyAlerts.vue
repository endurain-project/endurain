<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Activity } from '@/features/activities/types'

import { Alert } from '@/components/ui/alert'
import { hasHiddenFields, isActivityOwner } from '@/features/activities/utils/privacy'

const props = defineProps<{
  activity: Activity
  /** The viewer's user id, or `null` when unauthenticated. */
  currentUserId: string | null
}>()

const { t } = useI18n()

const isOwner = computed(() => isActivityOwner(props.activity, props.currentUserId))
const showHidden = computed(() => isOwner.value && props.activity.isHidden)
const showPrivacy = computed(() => isOwner.value && hasHiddenFields(props.activity))
</script>

<template>
  <div v-if="showHidden || showPrivacy" class="flex flex-col gap-2">
    <Alert v-if="showHidden" kind="warning">{{ t('activities.alerts.hidden') }}</Alert>
    <Alert v-if="showPrivacy" kind="info">{{ t('activities.alerts.privacy') }}</Alert>
  </div>
</template>
