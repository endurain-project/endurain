<script setup lang="ts">
import { MapPin } from '@lucide/vue'

import type { PublicUser } from '@/features/users/types'

import { Card } from '@/components/ui/card'
import UserAvatar from '@/components/UserAvatar.vue'

defineProps<{
  /** The public user whose identity to render. */
  user: PublicUser
}>()
</script>

<template>
  <Card class="flex flex-col items-center gap-3 text-center">
    <UserAvatar :src="user.avatarUrl" :alt="user.name" size-class="size-24" icon-class="size-12" />
    <div class="min-w-0">
      <p class="truncate text-card-heading">
        <bdi>{{ user.name }}</bdi>
      </p>
      <p class="truncate text-caption">@{{ user.username }}</p>
      <p v-if="user.city" class="mt-1 flex items-center justify-center gap-1 text-hint">
        <MapPin class="size-3.5 shrink-0" aria-hidden="true" />
        <span class="truncate">{{ user.city }}</span>
      </p>
    </div>
  </Card>
</template>
