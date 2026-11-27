<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Check, Clock, UserPlus } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useToasts } from '@/composables/useToasts'
import {
  useFollowStatusQuery,
  useFollowUserMutation,
  useUnfollowUserMutation,
} from '@/features/followers/composables/useFollowers'

const props = defineProps<{
  /** The profile owner the viewer may follow. */
  targetUserId: string
  /** The profile owner's display name, interpolated into the confirm copy. */
  targetName: string
}>()

const { t } = useI18n()
const toasts = useToasts()

const statusQuery = useFollowStatusQuery(() => props.targetUserId)
const status = computed(() => statusQuery.data.value ?? 'none')

const followMutation = useFollowUserMutation()
const unfollowMutation = useUnfollowUserMutation()
const isBusy = computed(() => followMutation.isPending.value || unfollowMutation.isPending.value)

const isConfirmOpen = ref(false)

/** Sends a follow request (or follows directly, per backend policy). */
function follow(): void {
  followMutation.mutate(props.targetUserId, {
    onError: () => toasts.error(t('userProfile.follow.followError')),
  })
}

function openConfirm(): void {
  isConfirmOpen.value = true
}

/** Withdraws a pending request or unfollows, after confirmation. */
function confirmUnfollow(): void {
  unfollowMutation.mutate(props.targetUserId, {
    onSuccess: () => {
      isConfirmOpen.value = false
    },
    onError: () => toasts.error(t('userProfile.follow.unfollowError')),
  })
}

const confirmTitle = computed(() =>
  status.value === 'pending'
    ? t('userProfile.follow.confirmCancelTitle', { name: props.targetName })
    : t('userProfile.follow.confirmUnfollowTitle', { name: props.targetName }),
)
const confirmBody = computed(() =>
  status.value === 'pending'
    ? t('userProfile.follow.confirmCancelBody', { name: props.targetName })
    : t('userProfile.follow.confirmUnfollowBody', { name: props.targetName }),
)
const confirmLabel = computed(() =>
  status.value === 'pending' ? t('userProfile.follow.withdraw') : t('userProfile.follow.unfollow'),
)
</script>

<template>
  <div>
    <Button v-if="status === 'none'" class="w-full" :disabled="isBusy" @click="follow">
      <UserPlus class="size-4" aria-hidden="true" />
      {{ t('userProfile.follow.follow') }}
    </Button>
    <Button
      v-else-if="status === 'pending'"
      variant="outline"
      class="w-full"
      :disabled="isBusy"
      @click="openConfirm"
    >
      <Clock class="size-4" aria-hidden="true" />
      {{ t('userProfile.follow.requested') }}
    </Button>
    <Button v-else variant="outline" class="w-full" :disabled="isBusy" @click="openConfirm">
      <Check class="size-4" aria-hidden="true" />
      {{ t('userProfile.follow.following') }}
    </Button>

    <ConfirmDialog
      v-model:open="isConfirmOpen"
      :title="confirmTitle"
      :description="confirmBody"
      :confirm-label="confirmLabel"
      :cancel-label="t('userProfile.follow.cancel')"
      :close-label="t('userProfile.follow.close')"
      :pending="unfollowMutation.isPending.value"
      @confirm="confirmUnfollow"
    />
  </div>
</template>
