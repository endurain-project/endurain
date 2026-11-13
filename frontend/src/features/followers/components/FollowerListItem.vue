<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Skeleton } from '@/components/ui/skeleton'
import UserAvatar from '@/components/UserAvatar.vue'
import { useToasts } from '@/composables/useToasts'
import { usePublicUserQuery } from '@/features/users/composables/usePublicUser'
import {
  useAcceptFollowerMutation,
  useRemoveFollowerMutation,
  useUnfollowUserMutation,
} from '@/features/followers/composables/useFollowers'

const props = defineProps<{
  /** The other user's id (the follower, or the followed user). */
  userId: string
  /** Whether this follow relationship is accepted (vs a pending request). */
  isAccepted: boolean
  /**
   * Which list this row belongs to: `follower` (someone following the profile
   * owner) or `following` (someone the profile owner follows). Drives which
   * management actions are offered.
   */
  relation: 'follower' | 'following'
  /** Whether the viewer owns this profile and may manage the relationship. */
  canManage: boolean
}>()

const { t } = useI18n()
const toasts = useToasts()

const userQuery = usePublicUserQuery(() => props.userId)
const user = computed(() => userQuery.data.value ?? null)
const userRoute = computed(() => ({ name: 'user', params: { id: props.userId } }))

const acceptMutation = useAcceptFollowerMutation()
const removeMutation = useRemoveFollowerMutation()
const unfollowMutation = useUnfollowUserMutation()

/** A pending incoming request (someone asking to follow the profile owner). */
const isPendingRequest = computed(() => props.relation === 'follower' && !props.isAccepted)

const isConfirmOpen = ref(false)
const isDestructiveBusy = computed(
  () => removeMutation.isPending.value || unfollowMutation.isPending.value,
)

/** Accepts an incoming follow request (non-destructive, no confirmation). */
function accept(): void {
  acceptMutation.mutate(props.userId, {
    onError: () => toasts.error(t('userProfile.list.acceptError')),
  })
}

function openConfirm(): void {
  isConfirmOpen.value = true
}

/** Runs the destructive action (unfollow, or decline/remove a follower). */
function confirmDestructive(): void {
  const onSuccess = () => {
    isConfirmOpen.value = false
  }
  if (props.relation === 'following') {
    unfollowMutation.mutate(props.userId, {
      onSuccess,
      onError: () => toasts.error(t('userProfile.list.unfollowError')),
    })
  } else {
    removeMutation.mutate(props.userId, {
      onSuccess,
      onError: () => toasts.error(t('userProfile.list.removeError')),
    })
  }
}

const displayName = computed(() => user.value?.name ?? '')

const confirmTitle = computed(() => {
  if (props.relation === 'following') {
    return t('userProfile.list.confirmUnfollowTitle', { name: displayName.value })
  }
  return isPendingRequest.value
    ? t('userProfile.list.confirmDeclineTitle', { name: displayName.value })
    : t('userProfile.list.confirmRemoveTitle', { name: displayName.value })
})
const confirmBody = computed(() => {
  if (props.relation === 'following') {
    return t('userProfile.list.confirmUnfollowBody', { name: displayName.value })
  }
  return isPendingRequest.value
    ? t('userProfile.list.confirmDeclineBody', { name: displayName.value })
    : t('userProfile.list.confirmRemoveBody', { name: displayName.value })
})
const confirmLabel = computed(() => {
  if (props.relation === 'following') {
    return t('userProfile.list.unfollow')
  }
  return isPendingRequest.value ? t('userProfile.list.decline') : t('userProfile.list.remove')
})
</script>

<template>
  <div class="flex items-center gap-3">
    <template v-if="user">
      <RouterLink :to="userRoute" class="flex min-w-0 flex-1 items-center gap-3 hover:underline">
        <UserAvatar
          :src="user.avatarUrl"
          :alt="user.name"
          size-class="size-11"
          icon-class="size-5"
        />
        <div class="min-w-0">
          <p class="truncate text-item-title">
            <bdi>{{ user.name }}</bdi>
          </p>
          <p class="truncate text-caption">@{{ user.username }}</p>
        </div>
      </RouterLink>

      <Badge :variant="isAccepted ? 'secondary' : 'warning'" class="shrink-0">
        {{ isAccepted ? t('userProfile.list.accepted') : t('userProfile.list.pending') }}
      </Badge>

      <div v-if="canManage" class="flex shrink-0 items-center gap-2">
        <Button
          v-if="isPendingRequest"
          size="sm"
          :disabled="acceptMutation.isPending.value"
          @click="accept"
        >
          {{ t('userProfile.list.accept') }}
        </Button>
        <Button variant="outline" size="sm" :disabled="isDestructiveBusy" @click="openConfirm">
          {{ confirmLabel }}
        </Button>
      </div>
    </template>

    <template v-else>
      <Skeleton class="size-11 rounded-full" />
      <div class="flex-1 space-y-2">
        <Skeleton class="h-4 w-1/3" />
        <Skeleton class="h-3 w-1/4" />
      </div>
    </template>

    <ConfirmDialog
      v-model:open="isConfirmOpen"
      :title="confirmTitle"
      :description="confirmBody"
      :confirm-label="confirmLabel"
      :cancel-label="t('userProfile.list.cancel')"
      :close-label="t('userProfile.list.close')"
      :pending="isDestructiveBusy"
      @confirm="confirmDestructive"
    />
  </div>
</template>
