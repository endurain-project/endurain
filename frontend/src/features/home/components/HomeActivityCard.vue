<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { Globe, Lock, Users } from '@lucide/vue'

import type { Activity, ActivityOwner } from '@/features/activities/types'
import type { Units } from '@/features/activities/utils/format'

import { Card } from '@/components/ui/card'
import { ActivityTypeBadge } from '@/components/ui/activity-type-badge'
import { Badge } from '@/components/ui/badge'
import { SafeHtml } from '@/components/federation'
import UserAvatar from '@/components/UserAvatar.vue'
import ActivityActionsMenu from '@/features/activities/components/ActivityActionsMenu.vue'
import ActivityGallery from '@/features/activities/components/ActivityGallery.vue'
import ActivityMetricsGrid from '@/features/activities/components/ActivityMetricsGrid.vue'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogos'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { useActivityOwnerQuery } from '@/features/activities/composables/useActivityDetail'
import { isAwaitingThumbnail } from '@/features/upload/composables/usePendingThumbnails'
import { formatZonedDateTime } from '@/utils/datetime'
import {
  activityTypeIsVirtual,
  presentActivityType,
} from '@/features/activities/utils/activityType'
import {
  buildMetricVisibility,
  canViewField,
  isActivityOwner,
} from '@/features/activities/utils/privacy'
import { cn } from '@/lib/utils'
import { getBackendAssetUrl } from '@/services/runtime'

const props = defineProps<{
  /** The feed activity to render. */
  activity: Activity
  /** The viewer's unit system. */
  units: Units
  /** The viewer's user id, or `null` when unauthenticated. */
  currentUserId: number | null
}>()

const { t, locale } = useI18n()

const { data: currentUser } = useCurrentUser()
const ownerQuery = useActivityOwnerQuery(() => props.activity)

const isOwner = computed(() => isActivityOwner(props.activity, props.currentUserId))

/** The activity owner's identity: self from cache, others from the query. */
const owner = computed<ActivityOwner | null>(() => {
  if (currentUser.value && isOwner.value) {
    return {
      name: currentUser.value.name,
      username: currentUser.value.username,
      avatarUrl: currentUser.value.avatarUrl,
    }
  }
  return ownerQuery.data.value ?? null
})

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

const metricVisibility = computed(() => buildMetricVisibility(props.activity, props.currentUserId))

/**
 * The map thumbnail URL, or `null` when there is no thumbnail or the viewer may
 * not see the map. The backend returns a ready-to-use URL: a same-origin signed
 * path (`/api/v1/activities/42/thumbnail?t=…`) for local storage, or an absolute
 * (presigned) URL for remote object storage; `getBackendAssetUrl` handles both.
 */
const thumbnailUrl = computed(() => {
  const path = props.activity.mapThumbnailPath
  if (!path || !canViewField(props.activity, 'hideMap', props.currentUserId)) {
    return null
  }
  return getBackendAssetUrl(path)
})

/**
 * Whether to hold the map slot with a placeholder: the activity was just
 * uploaded and its thumbnail is still being rendered by a background job. Only
 * ever true for activities this session uploaded, so the many activities that
 * legitimately have no map (no GPS track) never show a placeholder.
 */
const thumbnailPending = computed(
  () =>
    thumbnailUrl.value === null &&
    canViewField(props.activity, 'hideMap', props.currentUserId) &&
    isAwaitingThumbnail(props.activity.id),
)

const activityRoute = computed(() => ({ name: 'activity', params: { id: props.activity.id } }))

/** Route to the activity owner's profile, when their user id is known. */
const ownerRoute = computed(() =>
  props.activity.userId ? { name: 'user', params: { id: props.activity.userId } } : null,
)
</script>

<template>
  <Card :class="cn('flex flex-col gap-3', activity.isHidden && 'border-effort/60')">
    <!-- Athlete header -->
    <div class="flex items-start justify-between gap-3">
      <div class="flex min-w-0 items-center gap-3">
        <UserAvatar
          :src="owner?.avatarUrl"
          :alt="owner?.name ?? ''"
          size-class="size-16"
          icon-class="size-5"
        />
        <div class="min-w-0">
          <p class="truncate text-item-title">
            <RouterLink v-if="owner && ownerRoute" :to="ownerRoute" class="hover:underline">
              {{ owner.name }}
            </RouterLink>
            <span v-else>{{ owner ? owner.name : t('activities.athlete') }}</span>
          </p>
          <div class="mt-1 flex flex-wrap items-center gap-2">
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
          <p v-if="dateTimeLabel || locationLabel" class="mt-1 text-caption">
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

    <!-- Title -->
    <RouterLink :to="activityRoute" class="text-card-heading hover:underline">
      {{ activity.name }}
    </RouterLink>

    <!-- Description -->
    <SafeHtml
      v-if="activity.description"
      :source="activity.description"
      markdown
      class="text-body"
    />

    <!-- Metrics -->
    <ActivityMetricsGrid :activity="activity" :units="units" :visibility="metricVisibility" />

    <!-- Media gallery: the static map thumbnail leads, then the photos. -->
    <ActivityGallery
      :points="[]"
      :thumbnail-url="thumbnailUrl"
      :thumbnail-to="activityRoute"
      :thumbnail-pending="thumbnailPending"
      :activity-id="activity.id"
      :is-owner="isOwner"
      height-class="h-65"
    />
  </Card>
</template>
