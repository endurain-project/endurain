<script setup lang="ts">
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
</script>

<template>
  <!--
    Placeholder mirroring HomeActivityCard's layout (athlete header, title,
    media). Reused for both the feed's initial load and the in-progress upload
    placeholder so a pending activity keeps the feed's visual rhythm.
  -->
  <Card class="flex flex-col gap-3" aria-hidden="true">
    <div class="flex items-center gap-3">
      <Skeleton class="size-11 rounded-full" />
      <div class="flex-1 space-y-2">
        <Skeleton class="h-4 w-1/3" />
        <Skeleton class="h-3 w-1/2" />
      </div>
    </div>
    <Skeleton class="h-5 w-2/3" />
    <Skeleton class="h-48 w-full rounded-card" />
  </Card>
</template>
