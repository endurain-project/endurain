<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Globe, Lock, Users } from '@lucide/vue'

import type { Activity, ActivityOwner } from '@/features/activities/types'
import type { Units } from '@/features/activities/utils/format'

import { ActivityTypeBadge } from '@/components/ui/activity-type-badge'
import { Badge } from '@/components/ui/badge'
import { SafeHtml } from '@/components/federation'
import UserAvatar from '@/components/UserAvatar.vue'
import ActivityActionsMenu from '@/features/activities/components/ActivityActionsMenu.vue'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogos'
import {
  activityTypeIsVirtual,
  presentActivityType,
} from '@/features/activities/utils/activityType'
import { canViewField, isActivityOwner } from '@/features/activities/utils/privacy'
import { formatZonedDateTime } from '@/utils/datetime'

const props = defineProps<{
  activity: Activity
  units: Units
  /** The viewer's user id, or `null` when unauthenticated. */
  currentUserId: number | null
  /** Owner identity, when known (e.g. the viewer's own activity). */
  owner?: ActivityOwner | null
}>()

const { t, locale } = useI18n()

const presentation = computed(() => presentActivityType(props.activity.activityType))
const isVirtual = computed(() => activityTypeIsVirtual(props.activity.activityType))

const VISIBILITY_LABEL_KEYS = [
  'activities.visibility.public',
  'activities.visibility.followers',
  'activities.visibility.private',
]
const VISIBILITY_ICONS = [Globe, Users, Lock]
const visibilityLabel = computed(
  () => VISIBILITY_LABEL_KEYS[props.activity.visibility] ?? 'activities.visibility.public',
)
const visibilityIcon = computed(() => VISIBILITY_ICONS[props.activity.visibility] ?? Globe)

const canSeeStartTime = computed(() =>
  canViewField(props.activity, 'hideStartTime', props.currentUserId),
)
const canSeeLocation = computed(() =>
  canViewField(props.activity, 'hideLocation', props.currentUserId),
)

const dateTimeLabel = computed(
  () =>
    formatZonedDateTime(props.activity.startTime, props.activity.timezone, locale.value, {
      dateStyle: 'medium',
      timeStyle: canSeeStartTime.value ? 'short' : undefined,
    }) || null,
)

const locationLabel = computed(() => {
  if (!canSeeLocation.value) {
    return null
  }
  const place = props.activity.city ?? props.activity.town
  return [place, props.activity.country].filter(Boolean).join(', ') || null
})

const stravaUrl = computed(() =>
  props.activity.stravaActivityId
    ? `https://www.strava.com/activities/${props.activity.stravaActivityId}`
    : null,
)
const garminUrl = computed(() =>
  props.activity.garminActivityId
    ? `https://connect.garmin.com/modern/activity/${props.activity.garminActivityId}`
    : null,
)

const isOwner = computed(() => isActivityOwner(props.activity, props.currentUserId))

const showPrivateNotes = computed(
  () => isActivityOwner(props.activity, props.currentUserId) && !!props.activity.privateNotes,
)
</script>

<template>
  <header class="flex flex-col gap-3">
    <!-- Athlete photo + name + meta on the left, external links on the right. -->
    <div class="flex items-start justify-between gap-3">
      <div class="flex min-w-0 items-center gap-3">
        <UserAvatar
          :src="owner?.avatarUrl"
          :alt="owner?.name ?? ''"
          size-class="size-16"
          icon-class="size-7"
        />
        <div class="min-w-0">
          <p class="truncate text-item-title">
            {{ owner ? owner.name : t('activities.athlete') }}
          </p>
          <div class="mt-1.5 flex flex-wrap items-center gap-2">
            <ActivityTypeBadge :type="presentation.badge" :icon="presentation.icon">
              {{ t(presentation.labelKey) }}
            </ActivityTypeBadge>
            <Badge v-if="isVirtual" variant="outline">{{ t('activities.virtual') }}</Badge>
            <Badge variant="secondary" class="gap-1">
              <component :is="visibilityIcon" class="size-3.5 shrink-0" aria-hidden="true" />
              {{ t(visibilityLabel) }}
            </Badge>
            <Badge v-if="activity.isHidden" variant="destructive">{{
              t('activities.hidden')
            }}</Badge>
          </div>
          <p v-if="dateTimeLabel || locationLabel" class="text-caption mt-1.5">
            <span v-if="dateTimeLabel">{{ dateTimeLabel }}</span>
            <span v-if="dateTimeLabel && locationLabel"> · </span>
            <span v-if="locationLabel">{{ locationLabel }}</span>
          </p>
        </div>
      </div>

      <div class="flex shrink-0 items-center gap-2">
        <a
          v-if="isOwner && stravaUrl"
          :href="stravaUrl"
          target="_blank"
          rel="noopener noreferrer"
          :aria-label="t('activities.openInStrava')"
          class="rounded-input p-1 hover:bg-accent"
        >
          <img :src="INTEGRATION_LOGOS.stravaMark" alt="" class="size-5 object-contain" />
        </a>
        <a
          v-if="isOwner && garminUrl"
          :href="garminUrl"
          target="_blank"
          rel="noopener noreferrer"
          :aria-label="t('activities.openInGarmin')"
          class="rounded-input p-1 hover:bg-accent"
        >
          <img :src="INTEGRATION_LOGOS.garminApp" alt="" class="size-5 rounded object-contain" />
        </a>
        <ActivityActionsMenu v-if="isOwner" :activity="activity" />
      </div>
    </div>

    <h1 class="text-page-title">{{ activity.name }}</h1>

    <SafeHtml
      v-if="activity.description"
      :source="activity.description"
      markdown
      class="text-body"
    />

    <div v-if="showPrivateNotes" class="rounded-input">
      <p class="text-caption mb-1">{{ t('activities.privateNotes') }}</p>
      <SafeHtml :source="activity.privateNotes" markdown class="text-body" />
    </div>
  </header>
</template>
