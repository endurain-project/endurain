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
          <router-link :to="{ name: 'activities' }" class="nav-link link-body-emphasis">
            <font-awesome-icon :icon="['fas', 'fa-person-running']" />
            <span class="ms-1">
              {{ $t('navbarComponent.activities') }}
            </span>
          </router-link>
          <!-- Summary link -->
          <router-link :to="{ name: 'summary' }" class="nav-link link-body-emphasis">
            <font-awesome-icon :icon="['fas', 'fa-calendar-alt']" />
            <span class="ms-1">
              {{ $t('navbarComponent.summary') }}
            </span>
          </router-link>
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
              <li>
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

<script>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
// Importing the i18n
import { useI18n } from 'vue-i18n'
// import the stores
import { useAuthStore } from '@/stores/authStore'
// Import Notivue push
import { push } from 'notivue'

import UserAvatarComponent from '@/components/Users/UserAvatarComponent.vue'
import NavbarPipeComponent from '@/components/Navbar/NavbarPipeComponent.vue'
import NavbarThemeSwitcherComponent from '@/components/Navbar/NavbarThemeSwitcherComponent.vue'
import NavbarLanguageSwitcherComponent from '@/components/Navbar/NavbarLanguageSwitcherComponent.vue'

export default {
  components: {
    UserAvatarComponent,
    NavbarPipeComponent,
    NavbarThemeSwitcherComponent,
    NavbarLanguageSwitcherComponent
  },
  setup() {
    const router = useRouter()
    const authStore = useAuthStore()
    const { locale, t } = useI18n()

    async function handleLogout() {
      try {
        await authStore.logoutUser(router, locale)
      } catch (error) {
        push.error(`${t('navbarComponent.errorLogout')} - ${error}`)
      }
    }

    return {
      authStore,
      handleLogout
    }
  }
}
</script>
