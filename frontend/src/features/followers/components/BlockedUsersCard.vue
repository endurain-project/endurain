<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import UserAvatar from '@/components/UserAvatar.vue'
import { useToasts } from '@/composables/useToasts'
import {
  useBlockedUsersQuery,
  useUnblockUserMutation,
} from '@/features/followers/composables/useFollowers'

const { t } = useI18n()
const toasts = useToasts()

const blockedQuery = useBlockedUsersQuery()
const unblockMutation = useUnblockUserMutation()

/**
 * Unblocks a user, surfacing a failure as a toast; the list refetches on settle.
 *
 * @param userId - The blocked user to unblock.
 */
function unblock(userId: string): void {
  unblockMutation.mutate(userId, {
    onError: () => toasts.error(t('settings.profile.blockedUsers.unblockError')),
  })
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-col gap-1">
      <h2 class="text-card-heading">{{ t('settings.profile.blockedUsers.title') }}</h2>
      <p class="text-body">{{ t('settings.profile.blockedUsers.subtitle') }}</p>
    </div>

    <div v-if="blockedQuery.isPending.value" class="flex flex-col gap-2" aria-busy="true">
      <Skeleton v-for="n in 2" :key="n" class="h-11 w-full" />
    </div>

    <ErrorState
      v-else-if="blockedQuery.isError.value"
      :title="t('settings.profile.blockedUsers.loadError')"
    >
      <template #action>
        <Button variant="outline" @click="blockedQuery.refetch()">
          {{ t('settings.profile.blockedUsers.retry') }}
        </Button>
      </template>
    </ErrorState>

    <EmptyState
      v-else-if="!blockedQuery.data.value?.length"
      variant="filtered"
      :title="t('settings.profile.blockedUsers.empty')"
    />

    <ul v-else class="flex flex-col gap-2">
      <li v-for="user in blockedQuery.data.value" :key="user.id" class="flex items-center gap-3">
        <RouterLink
          :to="{ name: 'user', params: { id: user.id } }"
          class="flex min-w-0 flex-1 items-center gap-3 hover:underline"
        >
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
        <Button
          variant="outline"
          size="sm"
          class="shrink-0"
          :disabled="unblockMutation.isPending.value"
          @click="unblock(user.id)"
        >
          {{ t('settings.profile.blockedUsers.unblock') }}
        </Button>
      </li>
    </ul>
  </Card>
</template>
