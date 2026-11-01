<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { ManagedUser } from '@/features/users/types'

import { Badge } from '@/components/ui/badge'

/**
 * The status/identity badges for a managed user (self, access tier, account
 * state, external auth). Shared by the users list row and the user detail page
 * so both stay in sync.
 */
defineProps<{
  /** The user to describe. */
  user: ManagedUser
  /** Whether this is the signed-in admin's own account. */
  isSelf: boolean
}>()

const { t } = useI18n()
</script>

<template>
  <div class="flex flex-wrap items-center gap-1.5">
    <Badge v-if="isSelf" variant="outline">{{ t('settings.users.list.you') }}</Badge>
    <Badge v-if="user.accessType === 'admin'" variant="info">{{
      t('settings.users.list.admin')
    }}</Badge>
    <Badge v-if="!user.active" variant="destructive">{{ t('settings.users.list.inactive') }}</Badge>
    <Badge v-if="!user.emailVerified" variant="warning">{{
      t('settings.users.list.unverified')
    }}</Badge>
    <Badge v-if="user.pendingEmail" variant="warning">{{
      t('settings.users.list.pendingEmail')
    }}</Badge>
    <Badge v-if="user.pendingAdminApproval" variant="warning">{{
      t('settings.users.list.pending')
    }}</Badge>
    <Badge v-if="user.externalAuthCount > 0" variant="secondary">{{
      t('settings.users.list.externalAuth')
    }}</Badge>
  </div>
</template>
