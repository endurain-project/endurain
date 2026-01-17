<template>
  <!-- info banner to display password complexity requirements -->
  <div class="alert alert-info alert-dismissible d-flex align-items-center" role="alert">
    <div>
      <strong>{{ $t('usersPasswordRequirementsComponent.passwordRequirementsTitle') }}</strong>
      <br />

      <!-- Display password type description -->
      <template v-if="passwordType === 'strict'">
        - {{ minLength }} {{ $t('usersPasswordRequirementsComponent.passwordCharacters') }}
        <br />
        {{ $t('usersPasswordRequirementsComponent.passwordCapitalLetters') }}
        <br />
        {{ $t('usersPasswordRequirementsComponent.passwordNumbers') }}
        <br />
        {{ $t('usersPasswordRequirementsComponent.passwordSpecialCharacters') }}
      </template>

      <template v-else-if="passwordType === 'length_only'">
        - {{ minLength }} {{ $t('usersPasswordRequirementsComponent.passwordCharacters') }}
      </template>

      <template v-else>
        {{ $t('usersPasswordRequirementsComponent.passwordRequirementsTitle') }}
        <br />
        {{ $t('usersPasswordRequirementsComponent.passwordCharacters') }}
        <span v-if="minLength" class="fw-bold">{{ minLength }}</span>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Password requirements info banner component.
 * Displays password policy requirements based on server settings.
 * Shows different requirements for strict, length_only policies.
 */

import { computed, type ComputedRef } from 'vue'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { useAuthStore } from '@/stores/authStore'

const serverSettingsStore = useServerSettingsStore()
const authStore = useAuthStore()

/**
 * Gets the current password type from server settings.
 *
 * @returns The password policy type ('strict', 'length_only').
 */
const passwordType: ComputedRef<string> = computed(
  () => serverSettingsStore.serverSettings.password_type
)

/**
 * Gets the minimum password length for regular users from server settings.
 *
 * @returns The minimum password length.
 */
const minLength: ComputedRef<number> = computed(() =>
  authStore.user.access_type === 'regular'
    ? serverSettingsStore.serverSettings.password_length_regular_users
    : serverSettingsStore.serverSettings.password_length_admin_users
)
</script>
