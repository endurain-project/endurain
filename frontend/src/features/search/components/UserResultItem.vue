<script setup lang="ts">
import { RouterLink } from 'vue-router'

import type { PublicUser } from '@/features/users/types'

import UserAvatar from '@/components/UserAvatar.vue'

/**
 * One user row in the search results: avatar, name, and `@username`, linking to
 * the public profile.
 */
defineProps<{ user: PublicUser }>()
</script>

<template>
  <RouterLink
    :to="{ name: 'user', params: { id: user.id } }"
    class="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-muted/50"
  >
    <span
      class="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-muted text-muted-foreground"
    >
      <UserAvatar :src="user.avatarUrl" :alt="user.name" size-class="size-10" icon-class="size-5" />
    </span>
    <div class="min-w-0 flex-1">
      <p class="truncate font-medium text-foreground">{{ user.name }}</p>
      <p class="truncate text-hint">@{{ user.username }}</p>
    </div>
  </RouterLink>
</template>
