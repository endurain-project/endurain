<template>
  <div class="col-lg-3 col-md-12">
    <ul
      class="nav nav-pills flex-column mb-auto bg-body-tertiary rounded p-3 shadow-sm"
      id="sidebarNav"
    >
      <li class="nav-item" v-if="authStore.user.access_type === 'admin'">
        <a
          href="#"
          class="nav-link link-body-emphasis"
          :class="{ active: activeSection === 'users' }"
          @click.prevent="changeActive('users')"
        >
          <font-awesome-icon :icon="['fas', 'fa-users']" />
          <span class="ms-1">{{ $t('settingsSideBar.usersSection') }}</span>
        </a>
      </li>
      <li class="nav-item" v-if="authStore.user.access_type === 'admin'">
        <a
          href="#"
          class="nav-link link-body-emphasis"
          :class="{ active: activeSection === 'serverSettings' }"
          @click.prevent="changeActive('serverSettings')"
        >
          <font-awesome-icon :icon="['fas', 'server']" />
          <span class="ms-1">{{ $t('settingsSideBar.serverSettingsSection') }}</span>
        </a>
      </li>
      <li class="nav-item" v-if="authStore.user.access_type === 'admin'">
        <a
          href="#"
          class="nav-link link-body-emphasis"
          :class="{ active: activeSection === 'identityProviders' }"
          @click.prevent="changeActive('identityProviders')"
        >
          <font-awesome-icon :icon="['fas', 'id-card']" />
          <span class="ms-1"
            >{{ $t('settingsSideBar.identityProvidersSection')
            }}{{ $t('generalItems.betaTag') }}</span
          >
        </a>
      </li>
      <hr v-if="authStore.user.access_type === 'admin'" />
      <li class="nav-item">
        <a
          href="#"
          class="nav-link link-body-emphasis"
          :class="{ active: activeSection === 'general' }"
          @click.prevent="changeActive('general')"
        >
          <font-awesome-icon :icon="['fas', 'gears']" />
          <span class="ms-1">{{ $t('settingsSideBar.generalSection') }}</span>
        </a>
      </li>
      <li class="nav-item">
        <a
          href="#"
          class="nav-link link-body-emphasis"
          :class="{ active: activeSection === 'myProfile' }"
          @click.prevent="changeActive('myProfile')"
        >
          <font-awesome-icon :icon="['fas', 'fa-address-card']" />
          <span class="ms-1">{{ $t('settingsSideBar.myProfileSection') }}</span>
        </a>
      </li>
      <li class="nav-item">
        <a
          href="#"
          class="nav-link link-body-emphasis"
          :class="{ active: activeSection === 'myGoals' }"
          @click.prevent="changeActive('myGoals')"
        >
          <font-awesome-icon :icon="['fas', 'fa-check-double']" />
          <span class="ms-1">{{ $t('settingsSideBar.myGoals') }}</span>
        </a>
      </li>
      <li class="nav-item">
        <a
          href="#"
          class="nav-link link-body-emphasis"
          :class="{ active: activeSection === 'security' }"
          @click.prevent="changeActive('security')"
        >
          <font-awesome-icon :icon="['fas', 'fa-shield']" />
          <span class="ms-1">{{ $t('settingsSideBar.securitySection') }}</span>
        </a>
      </li>
      <li class="nav-item">
        <a
          href="#"
          class="nav-link link-body-emphasis"
          :class="{ active: activeSection === 'integrations' }"
          @click.prevent="changeActive('integrations')"
        >
          <font-awesome-icon :icon="['fas', 'fa-puzzle-piece']" />
          <span class="ms-1">{{ $t('settingsSideBar.integrationsSection') }}</span>
        </a>
      </li>
      <li class="nav-item">
        <a
          href="#"
          class="nav-link link-body-emphasis"
          :class="{ active: activeSection === 'import' }"
          @click.prevent="changeActive('import')"
        >
          <font-awesome-icon :icon="['fas', 'fa-upload']" />
          <span class="ms-1">{{ $t('settingsSideBar.importSection') }}</span>
        </a>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '@/stores/authStore'

/**
 * Component props definition.
 */
defineProps<{
  /** Currently active section identifier */
  activeSection: string
}>()

/**
 * Component emits definition.
 */
const emit = defineEmits<{
  /** Emitted when active section should be updated */
  updateActiveSection: [section: string]
}>()

const authStore = useAuthStore()

/**
 * Changes the active sidebar section.
 *
 * @param section - The section identifier to activate.
 */
function changeActive(section: string): void {
  emit('updateActiveSection', section)
}
</script>
