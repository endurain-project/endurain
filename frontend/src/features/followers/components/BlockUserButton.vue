<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ban } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useToasts } from '@/composables/useToasts'
import {
  useBlockUserMutation,
  useIsBlockedQuery,
  useUnblockUserMutation,
} from '@/features/followers/composables/useFollowers'

const props = defineProps<{
  /** The profile owner the viewer may block. */
  targetUserId: string
  /** The profile owner's display name, interpolated into the confirm copy. */
  targetName: string
}>()

const { t } = useI18n()
const toasts = useToasts()

const blockedQuery = useIsBlockedQuery(() => props.targetUserId)
const isBlocked = computed(() => blockedQuery.data.value ?? false)

const blockMutation = useBlockUserMutation()
const unblockMutation = useUnblockUserMutation()
const isBusy = computed(() => blockMutation.isPending.value || unblockMutation.isPending.value)

const isConfirmOpen = ref(false)

/** Blocks the user, after confirmation. */
function confirmBlock(): void {
  blockMutation.mutate(props.targetUserId, {
    onSuccess: () => {
      isConfirmOpen.value = false
    },
    onError: () => toasts.error(t('userProfile.block.blockError')),
  })
}

/** Unblocks the user straight away: it grants nothing the viewer cannot undo. */
function unblock(): void {
  unblockMutation.mutate(props.targetUserId, {
    onError: () => toasts.error(t('userProfile.block.unblockError')),
  })
}
</script>

<template>
  <div>
    <Button v-if="isBlocked" variant="outline" class="w-full" :disabled="isBusy" @click="unblock">
      <Ban class="size-4" aria-hidden="true" />
      {{ t('userProfile.block.unblock') }}
    </Button>
    <Button
      v-else
      variant="outline"
      class="w-full"
      :disabled="isBusy"
      @click="isConfirmOpen = true"
    >
      <Ban class="size-4" aria-hidden="true" />
      {{ t('userProfile.block.block') }}
    </Button>

    <ConfirmDialog
      v-model:open="isConfirmOpen"
      :title="t('userProfile.block.confirmTitle', { name: targetName })"
      :description="t('userProfile.block.confirmBody', { name: targetName })"
      :confirm-label="t('userProfile.block.block')"
      :cancel-label="t('userProfile.follow.cancel')"
      :close-label="t('userProfile.follow.close')"
      :pending="blockMutation.isPending.value"
      @confirm="confirmBlock"
    />
  </div>
</template>
