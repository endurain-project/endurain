<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { Check, KeyRound, Pencil, Trash2, X } from '@lucide/vue'

import type { ManagedUser } from '@/features/users/types'

import UserAvatar from '@/components/UserAvatar.vue'
import UserStatusBadges from '@/features/users/components/UserStatusBadges.vue'
import { Button } from '@/components/ui/button'

/**
 * One row in the admin users list: avatar, identity, status badges, and the
 * reset-password / edit / delete actions. Deleting the current user is
 * disallowed, so the delete action is hidden for the signed-in admin's own row.
 * A sign-up awaiting approval also gets approve / reject actions, disabled until
 * the user's email is verified.
 */
defineProps<{
  /** The user to render. */
  user: ManagedUser
  /** Whether this row is the signed-in admin's own account. */
  isSelf: boolean
}>()

const emit = defineEmits<{
  password: [user: ManagedUser]
  edit: [user: ManagedUser]
  delete: [user: ManagedUser]
  approve: [user: ManagedUser]
  reject: [user: ManagedUser]
}>()

const { t } = useI18n()
</script>

<template>
  <div class="flex items-center justify-between gap-3 px-4 py-3">
    <div class="flex min-w-0 items-center gap-3">
      <span
        class="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-muted text-muted-foreground"
      >
        <UserAvatar
          :src="user.avatarUrl"
          :alt="user.name"
          size-class="size-10"
          icon-class="size-5"
        />
      </span>
      <div class="min-w-0">
        <RouterLink
          :to="{ name: 'settings-user-detail', params: { id: user.id } }"
          class="block truncate font-medium text-foreground hover:underline"
        >
          {{ user.name }}
        </RouterLink>
        <p class="truncate text-hint">@{{ user.username }} · {{ user.email }}</p>
        <UserStatusBadges :user="user" :is-self="isSelf" class="mt-1" />
      </div>
    </div>
    <div class="flex shrink-0 items-center gap-1">
      <template v-if="user.pendingAdminApproval">
        <Button
          variant="ghost"
          size="icon-sm"
          :disabled="!user.emailVerified"
          :aria-label="t('settings.users.approval.approve')"
          @click="emit('approve', user)"
        >
          <Check class="size-4" aria-hidden="true" />
        </Button>
        <Button
          variant="ghostDestructive"
          size="icon-sm"
          :disabled="!user.emailVerified"
          :aria-label="t('settings.users.approval.reject')"
          @click="emit('reject', user)"
        >
          <X class="size-4" aria-hidden="true" />
        </Button>
      </template>
      <Button
        variant="ghost"
        size="icon-sm"
        :aria-label="t('settings.users.actions.resetPassword')"
        @click="emit('password', user)"
      >
        <KeyRound class="size-4" aria-hidden="true" />
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        :aria-label="t('settings.users.actions.edit')"
        @click="emit('edit', user)"
      >
        <Pencil class="size-4" aria-hidden="true" />
      </Button>
      <Button
        v-if="!isSelf"
        variant="ghostDestructive"
        size="icon-sm"
        :aria-label="t('settings.users.actions.delete')"
        @click="emit('delete', user)"
      >
        <Trash2 class="size-4" aria-hidden="true" />
      </Button>
    </div>
  </div>
</template>
