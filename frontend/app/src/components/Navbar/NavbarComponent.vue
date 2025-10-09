<template>
  <nav class="navbar navbar-expand-lg bg-body-tertiary">
    <div class="container-fluid">
      <!-- Navbar brand + search in the left -->
      <router-link :to="{ name: 'home' }" class="navbar-brand d-flex align-items-center">
        <img src="/logo/logo.svg" alt="Logo" width="24" height="24" class="me-2 rounded" />
        Endurain
      </router-link>

      <div class="d-none d-lg-flex w-100 justify-content-between">
        <div class="navbar-nav me-auto" v-if="authStore.isAuthenticated">
          <NavbarPipeComponent />

          <!-- Search -->
          <router-link :to="{ name: 'search' }" class="nav-link link-body-emphasis">
            <font-awesome-icon :icon="['fas', 'magnifying-glass']" />
            <span class="ms-1">
              {{ $t('navbarComponent.search') }}
            </span>
          </router-link>
        </div>

        <!-- Navigation middle -->
        <div class="navbar-nav mx-auto" v-if="authStore.isAuthenticated">
          <!-- if is logged in show activities button -->
          <li class="nav-item dropdown">
            <a
              class="nav-link dropdown-toggle link-body-emphasis"
              href="#"
              role="button"
              data-bs-toggle="dropdown"
              aria-expanded="false"
            >
              <font-awesome-icon :icon="['fas', 'fa-person-running']" />
              <span class="ms-1">
                {{ $t('navbarComponent.activities') }}
              </span>
            </a>
            <ul class="dropdown-menu">
              <li>
                <!-- Activities list link -->
                <router-link :to="{ name: 'activities' }" class="dropdown-item link-body-emphasis">
                  <font-awesome-icon :icon="['fas', 'fa-list']" />
                  <span class="ms-2">
                    {{ $t('navbarComponent.activitiesList') }}
                  </span>
                </router-link>
              </li>
              <li>
                <!-- Summary link -->
                <router-link :to="{ name: 'summary' }" class="dropdown-item link-body-emphasis">
                  <font-awesome-icon :icon="['fas', 'fa-calendar-alt']" />
                  <span class="ms-2">
                    {{ $t('navbarComponent.summary') }}
                  </span>
                </router-link>
								<!-- Segments link -->
								 <router-link :to="{ name: 'segments' }" class="dropdown-item link-body-emphasis">
									<font-awesome-icon :icon="['fas', 'fa-route']" />
									<span class="ms-2">
										{{ $t('navbarComponent.segments') }}
									</span>
								</router-link>
              </li>
            </ul>
          </li>
          <!-- if is logged in show gears button -->
          <router-link :to="{ name: 'gears' }" class="nav-link link-body-emphasis">
            <font-awesome-icon :icon="['fas', 'fa-bicycle']" />
            <span class="ms-1">
              {{ $t('navbarComponent.gear') }}
            </span>
          </router-link>
          <!-- if is logged in show health button -->
          <router-link :to="{ name: 'health' }" class="nav-link link-body-emphasis">
            <font-awesome-icon :icon="['fas', 'fa-heart']" />
            <span class="ms-1">
              {{ $t('navbarComponent.health') }}
            </span>
          </router-link>
        </div>

        <!-- Navigation end -->
        <div class="navbar-nav ms-auto" v-if="authStore.isAuthenticated">
          <NavbarNotificationsComponent />

          <NavbarPipeComponent />

          <NavbarLanguageSwitcherComponent />

          <NavbarThemeSwitcherComponent />

          <!-- Settings button -->
          <router-link :to="{ name: 'settings' }" class="nav-link link-body-emphasis">
            <font-awesome-icon :icon="['fas', 'fa-gear']" />
            <span class="ms-1 d-lg-none">{{ $t('navbarComponent.settings') }}</span>
          </router-link>

          <li class="nav-item dropdown">
            <a
              class="nav-link dropdown-toggle"
              href="#"
              role="button"
              data-bs-toggle="dropdown"
              aria-expanded="false"
            >
              <UserAvatarComponent :user="authStore.user" :width="24" :height="24" :alignTop="2" />
            </a>
            <ul class="dropdown-menu dropdown-menu-end">
              <li v-if="authStore.isAuthenticated && authStore.user.id">
                <router-link
                  :to="{ name: 'user', params: { id: authStore.user.id } }"
                  class="dropdown-item"
                >
                  <font-awesome-icon :icon="['fas', 'circle-user']" />
                  <span class="ms-2">{{ $t('navbarComponent.profile') }}</span>
                </router-link>
              </li>
              <li>
                <hr class="dropdown-divider" />
              </li>
              <li>
                <a class="dropdown-item" href="#" @click="handleLogout">
                  <font-awesome-icon :icon="['fas', 'fa-sign-out-alt']" />
                  <span class="ms-2">{{ $t('navbarComponent.logout') }}</span>
                </a>
              </li>
            </ul>
          </li>
        </div>
      </div>
      <div class="navbar-nav" v-if="!authStore.isAuthenticated">
        <router-link
          :to="{ name: 'login' }"
          class="nav-link link-body-emphasis d-flex align-items-center"
        >
          <font-awesome-icon :icon="['fas', 'fa-sign-in-alt']" />
          <span class="ms-1">{{ $t('navbarComponent.login') }}</span>
        </router-link>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { useRouter } from 'vue-router'
// Importing the i18n
import { useI18n } from 'vue-i18n'
// import the stores
import { useAuthStore } from '@/stores/authStore'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
// Import Notivue push
import { push } from 'notivue'

import UserAvatarComponent from '@/components/Users/UserAvatarComponent.vue'
import NavbarPipeComponent from '@/components/Navbar/NavbarPipeComponent.vue'
import NavbarThemeSwitcherComponent from '@/components/Navbar/NavbarThemeSwitcherComponent.vue'
import NavbarLanguageSwitcherComponent from '@/components/Navbar/NavbarLanguageSwitcherComponent.vue'
import NavbarNotificationsComponent from '@/components/Navbar/NavbarNotificationsComponent.vue'

// Composables
const router = useRouter()
const authStore = useAuthStore()
const serverSettingsStore = useServerSettingsStore()
const { locale, t } = useI18n()

// Methods
async function handleLogout() {
  try {
    await authStore.logoutUser(router, locale)
    serverSettingsStore.setServerSettingsOnLogout()
  } catch (error) {
    push.error(`${t('navbarComponent.errorLogout')} - ${error}`)
  }
}
</script>
