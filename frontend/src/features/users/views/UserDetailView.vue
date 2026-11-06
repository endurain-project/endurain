<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Check, KeyRound, Pencil, Trash2, Upload, X } from '@lucide/vue'

import { IMAGE_ACCEPTED_TYPES } from '@/lib/imageTypes'
import UserAvatar from '@/components/UserAvatar.vue'
import UserDeleteDialog from '@/features/users/components/UserDeleteDialog.vue'
import UserFormDialog from '@/features/users/components/UserFormDialog.vue'
import UserIdentityProvidersList from '@/features/users/components/UserIdentityProvidersList.vue'
import UserPasswordDialog from '@/features/users/components/UserPasswordDialog.vue'
import UserSessionsList from '@/features/users/components/UserSessionsList.vue'
import UserStatusBadges from '@/features/users/components/UserStatusBadges.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { useToasts } from '@/composables/useToasts'
import { consumeIdpStepUpReturn } from '@/features/security/composables/useIdpStepUp'
import { formatMediumDateTime } from '@/utils/datetime'
import {
  useApproveUserMutation,
  useDeleteUserPhotoMutation,
  useUploadUserPhotoMutation,
  useUserQuery,
} from '@/features/users/composables/useUsers'

/**
 * Admin detail page for a single user (`/settings/users/:id`). Renders the
 * account identity and hosts the per-user admin actions — starting with the
 * password reset; photo management and sessions land here next.
 */
const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const toasts = useToasts()
const { data: currentUser } = useCurrentUser()

// Returning from an identity-provider sign-in, the callback leaves its outcome in the URL fragment. It is
// consumed once; the dialog that started it reopens for the same user, and a failure is reported once the
// page is shown.
const stepUpReturn = consumeIdpStepUpReturn()
const resume = stepUpReturn && !stepUpReturn.error ? stepUpReturn : null
onMounted(() => {
  if (stepUpReturn?.error === 'not_fresh') {
    toasts.error(t('settings.security.stepUp.notFresh'))
  } else if (stepUpReturn?.error) {
    toasts.error(t('settings.security.stepUp.failed'))
  }
})

// A non-numeric or non-positive `:id` resolves to `null`, which keeps the query
// disabled and surfaces the not-found state below.
const userId = computed(() => {
  const raw = Number(route.params.id)
  return Number.isFinite(raw) && raw > 0 ? raw : null
})

const { data: user, isPending, isError, refetch } = useUserQuery(userId)

/** Whether this detail page is the signed-in admin's own account. */
const isSelf = computed(() => Boolean(user.value && currentUser.value?.id === user.value.id))

const isPasswordOpen = ref(false)

function onPasswordSuccess(message: string): void {
  toasts.success(message)
}

function onPasswordError(message: string): void {
  toasts.error(message)
}

// Edit reuses the shared add/edit form, pre-filled with the loaded user.
const isFormOpen = ref(false)

function onFormSuccess(message: string): void {
  toasts.success(message)
}

function onFormError(message: string): void {
  toasts.error(message)
}

// Delete mirrors the list action: confirm with the administrator's step-up, delete, then return to the
// list (this page would otherwise resolve to "not found"). Self-delete is disallowed.
const isDeleteOpen = ref(false)

function onDeleted(): void {
  void router.push({ name: 'settings-users' })
}

// Photo management: a hidden file input drives the upload. The backend validates
// the image authoritatively, so the client check is just fail-fast UX.
const fileInput = ref<HTMLInputElement | null>(null)
const uploadPhotoMutation = useUploadUserPhotoMutation()
const deletePhotoMutation = useDeleteUserPhotoMutation()
const isRemovePhotoOpen = ref(false)

/** Largest image the client will attempt to upload (the backend re-checks). */
const MAX_PHOTO_BYTES = 10 * 1024 * 1024

/** Validates and uploads the selected image, then clears the input. */
function onPhotoSelected(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  // Reset so selecting the same file again still re-triggers `change`.
  input.value = ''
  const target = user.value
  if (!file || !target) {
    return
  }
  if (!file.type.startsWith('image/') || file.size === 0 || file.size > MAX_PHOTO_BYTES) {
    toasts.error(t('settings.users.photo.invalid'))
    return
  }
  uploadPhotoMutation.mutate(
    { userId: target.id, file },
    {
      onSuccess: () => toasts.success(t('settings.users.photo.uploadSuccess')),
      onError: () => toasts.error(t('settings.users.photo.uploadError')),
    },
  )
}

/** Removes the user's current photo. */
function removePhoto(): void {
  const target = user.value
  if (!target) {
    return
  }
  deletePhotoMutation.mutate(target.id, {
    onSuccess: () => {
      isRemovePhotoOpen.value = false
      toasts.success(t('settings.users.photo.removeSuccess'))
    },
    onError: () => toasts.error(t('settings.users.photo.removeError')),
  })
}

// Pending sign-up moderation: approve clears the pending flag; reject deletes the
// account (after the administrator's step-up) and returns to the list.
const approveMutation = useApproveUserMutation()
const isRejectOpen = ref(false)

/** Approves the pending sign-up. */
function approve(): void {
  const target = user.value
  if (!target) {
    return
  }
  approveMutation.mutate(target.id, {
    onSuccess: () => toasts.success(t('settings.users.approval.approveSuccess')),
    onError: () => toasts.error(t('settings.users.approval.approveError')),
  })
}
</script>

<template>
  <section class="flex flex-col gap-3">
    <RouterLink
      :to="{ name: 'settings-users' }"
      class="inline-flex items-center gap-1 self-start text-meta text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft class="size-4" aria-hidden="true" />
      {{ t('settings.users.detail.back') }}
    </RouterLink>

    <!-- Loading: mirror the identity card, the security card, and the two list
         cards (identity providers + sessions) so the placeholder matches. -->
    <template v-if="userId && isPending">
      <Card
        class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
        aria-busy="true"
      >
        <div class="flex min-w-0 items-center gap-3">
          <Skeleton class="size-16 shrink-0 rounded-full" />
          <div class="space-y-2">
            <Skeleton class="h-6 w-40" />
            <Skeleton class="h-4 w-56" />
            <Skeleton class="h-5 w-32 rounded-full" />
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <Skeleton class="h-9 w-20" />
          <Skeleton class="h-9 w-24" />
        </div>
      </Card>
      <Card class="flex flex-col gap-3" aria-busy="true">
        <Skeleton class="h-5 w-40" />
        <Skeleton class="h-3 w-64" />
        <Skeleton class="h-9 w-44" />
      </Card>
      <Card
        v-for="n in 2"
        :key="n"
        padding="none"
        class="divide-y divide-border overflow-hidden"
        aria-busy="true"
      >
        <div class="px-4 py-3">
          <Skeleton class="h-5 w-40" />
        </div>
        <div class="divide-y divide-border">
          <div
            v-for="row in 2"
            :key="row"
            class="flex items-center justify-between gap-3 px-4 py-3"
          >
            <div class="space-y-2">
              <Skeleton class="h-4 w-32" />
              <Skeleton class="h-3 w-24" />
            </div>
            <Skeleton class="h-8 w-20" />
          </div>
        </div>
      </Card>
    </template>

    <!-- Error -->
    <ErrorState
      v-else-if="isError"
      :title="t('settings.users.detail.error.title')"
      :description="t('settings.users.detail.error.description')"
      @retry="() => refetch()"
    >
      <template #action="{ retry }">
        <Button variant="outline" @click="retry">
          {{ t('settings.users.detail.error.retry') }}
        </Button>
      </template>
    </ErrorState>

    <!-- Not found (bad id or deleted) -->
    <Card v-else-if="!user" class="text-center">
      <p class="text-card-heading">{{ t('settings.users.detail.notFoundTitle') }}</p>
      <p class="mt-1 text-hint">{{ t('settings.users.detail.notFoundDescription') }}</p>
    </Card>

    <!-- Loaded -->
    <template v-else>
      <Card class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex min-w-0 items-center gap-3">
          <span
            class="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-full bg-muted text-muted-foreground"
          >
            <UserAvatar
              :src="user.avatarUrl"
              :alt="user.name"
              size-class="size-16"
              icon-class="size-7"
            />
          </span>
          <div class="min-w-0">
            <h1 class="truncate text-page-title">
              <bdi>{{ user.name }}</bdi>
            </h1>
            <p class="truncate text-body">@{{ user.username }} · {{ user.email }}</p>
            <p v-if="user.pendingEmail && user.pendingEmailExpiresAt" class="text-hint">
              {{
                t('settings.users.detail.pendingEmail', {
                  email: user.pendingEmail,
                  date: formatMediumDateTime(user.pendingEmailExpiresAt, locale),
                })
              }}
            </p>
            <UserStatusBadges :user="user" :is-self="isSelf" class="mt-2" />
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" @click="isFormOpen = true">
            <Pencil class="size-4" aria-hidden="true" />
            {{ t('settings.users.actions.edit') }}
          </Button>
          <input
            ref="fileInput"
            type="file"
            :accept="IMAGE_ACCEPTED_TYPES.join(',')"
            class="hidden"
            @change="onPhotoSelected"
          />
          <Button
            variant="outline"
            size="sm"
            :disabled="uploadPhotoMutation.isPending.value"
            @click="fileInput?.click()"
          >
            <Upload class="size-4" aria-hidden="true" />
            {{ t('settings.users.photo.upload') }}
          </Button>
          <Button
            v-if="user.avatarUrl"
            variant="outlineDestructive"
            size="sm"
            :disabled="deletePhotoMutation.isPending.value"
            @click="isRemovePhotoOpen = true"
          >
            {{ t('settings.users.photo.remove') }}
          </Button>
          <Button v-if="!isSelf" variant="destructive" size="sm" @click="isDeleteOpen = true">
            <Trash2 class="size-4" aria-hidden="true" />
            {{ t('settings.users.actions.delete') }}
          </Button>
        </div>
      </Card>

      <!-- Pending sign-up moderation -->
      <Card v-if="user.pendingAdminApproval" class="flex flex-col gap-3">
        <div class="flex flex-col gap-1">
          <h2 class="text-card-heading">{{ t('settings.users.approval.title') }}</h2>
          <p class="text-hint">{{ t('settings.users.approval.subtitle') }}</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button
            :disabled="approveMutation.isPending.value || !user.emailVerified"
            @click="approve"
          >
            <Check class="size-4" aria-hidden="true" />
            {{ t('settings.users.approval.approve') }}
          </Button>
          <Button
            variant="destructive"
            :disabled="!user.emailVerified"
            @click="isRejectOpen = true"
          >
            <X class="size-4" aria-hidden="true" />
            {{ t('settings.users.approval.reject') }}
          </Button>
        </div>
        <p v-if="!user.emailVerified" class="text-hint">
          {{ t('settings.users.approval.emailUnverifiedHint') }}
        </p>
      </Card>

      <Card class="flex flex-col gap-3">
        <div class="flex flex-col gap-1">
          <h2 class="text-card-heading">{{ t('settings.users.detail.securityTitle') }}</h2>
          <p class="text-hint">{{ t('settings.users.detail.securitySubtitle') }}</p>
        </div>
        <Button variant="outline" class="self-start" @click="isPasswordOpen = true">
          <KeyRound class="size-4" aria-hidden="true" />
          {{ t('settings.users.password.button') }}
        </Button>
      </Card>

      <UserIdentityProvidersList :user-id="user.id" :resume="resume" />

      <UserSessionsList :user-id="user.id" />

      <UserPasswordDialog
        v-model:open="isPasswordOpen"
        :user-id="user.id"
        :username="user.username"
        :access-type="user.accessType"
        :resume="resume"
        @success="onPasswordSuccess"
        @error="onPasswordError"
      />

      <ConfirmDialog
        v-model:open="isRemovePhotoOpen"
        :title="t('settings.users.photo.removeTitle')"
        :description="t('settings.users.photo.removeBody', { username: user.username })"
        :confirm-label="t('settings.users.photo.removeConfirm')"
        :cancel-label="t('settings.users.photo.removeCancel')"
        :close-label="t('settings.users.photo.removeClose')"
        :pending="deletePhotoMutation.isPending.value"
        @confirm="removePhoto"
      />

      <UserDeleteDialog
        v-model:open="isRejectOpen"
        :user="user"
        variant="reject"
        :resume="resume"
        @success="onDeleted"
      />

      <UserFormDialog
        v-model:open="isFormOpen"
        :user="user"
        :is-self="isSelf"
        :resume="resume"
        @success="onFormSuccess"
        @error="onFormError"
      />

      <UserDeleteDialog
        v-model:open="isDeleteOpen"
        :user="user"
        variant="delete"
        :resume="resume"
        @success="onDeleted"
      />
    </template>
  </section>
</template>
