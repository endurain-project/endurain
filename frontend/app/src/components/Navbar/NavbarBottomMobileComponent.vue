<template>
  <nav class="navbar bg-body-tertiary text-center" v-if="authStore.isAuthenticated">
    <div class="container-fluid justify-content-around">
      <router-link :to="{ name: 'home' }" class="nav-link link-body-emphasis">
        <font-awesome-icon :icon="['fas', 'fa-home']" />
        <br />
        {{ $t('navbarBottomMobileComponent.home') }}
      </router-link>
      <router-link :to="{ name: 'activities' }" class="nav-link link-body-emphasis">
        <!-- Corrected route name -->
        <font-awesome-icon :icon="['fas', 'fa-person-running']" />
        <br />
        {{ $t('navbarBottomMobileComponent.activities') }}
      </router-link>
      <router-link :to="{ name: 'summary' }" class="nav-link link-body-emphasis">
        <font-awesome-icon :icon="['fas', 'fa-calendar-alt']" />
        <br />
        {{ $t('navbarBottomMobileComponent.summary') }}
      </router-link>
      <router-link :to="{ name: 'gears' }" class="nav-link link-body-emphasis">
        <font-awesome-icon :icon="['fas', 'fa-bicycle']" />
        <br />
        {{ $t('navbarBottomMobileComponent.gear') }}
      </router-link>
      <!--<router-link :to="{ name: 'menu' }" class="nav-link link-body-emphasis">
                <font-awesome-icon :icon="['fas', 'bars']" size="2x"/>
                <br>
                {{ $t("navbarBottomMobileComponent.menu") }}
            </router-link>-->
      <button
        class="nav-link link-body-emphasis"
        id="offcanvasNavbarButton"
        type="button"
        data-bs-toggle="offcanvas"
        data-bs-target="#offcanvasNavbar"
        aria-controls="offcanvasNavbar"
        aria-label="Toggle navigation"
      >
        <font-awesome-icon :icon="['fas', 'bars']" />
        <br />
        {{ $t('navbarBottomMobileComponent.menu') }}
      </button>
      <div
        class="offcanvas offcanvas-end"
        tabindex="-1"
        id="offcanvasNavbar"
        aria-labelledby="offcanvasNavbarLabel"
      >
        <div class="offcanvas-header">
          <h3 class="offcanvas-title" id="offcanvasNavbarLabel">
            {{ $t('navbarBottomMobileComponent.menu') }}
          </h3>
          <button
            type="button"
            class="btn-close"
            data-bs-dismiss="offcanvas"
            aria-label="Close"
          ></button>
        </div>
        <div class="offcanvas-body">
          <ul class="navbar-nav justify-content-end flex-grow-1 pe-3">
            <li class="nav-item">
              <router-link
                :to="{ name: 'health' }"
                class="nav-link link-body-emphasis w-100 py-3 fs-5"
                @click="closeOffcanvas"
              >
                <font-awesome-icon :icon="['fas', 'fa-heart']" />
                <span class="ms-1">{{ $t('navbarComponent.health') }}</span>
              </router-link>
            </li>
            <li class="nav-item">
              <router-link
                :to="{ name: 'search' }"
                class="nav-link link-body-emphasis w-100 py-3 fs-5"
                @click="closeOffcanvas"
              >
                <font-awesome-icon :icon="['fas', 'magnifying-glass']" />
                <span class="ms-1">{{ $t('navbarComponent.search') }}</span>
              </router-link>
            </li>
            <li class="nav-item">
              <router-link
                :to="{ name: 'settings' }"
                class="nav-link link-body-emphasis w-100 py-3 fs-5"
                @click="closeOffcanvas"
              >
                <font-awesome-icon :icon="['fas', 'fa-gear']" />
                <span class="ms-1">{{ $t('navbarComponent.settings') }}</span>
              </router-link>
            </li>
            <li class="nav-item">
              <router-link
                :to="{ name: 'user', params: { id: authStore.user.id } }"
                class="nav-link link-body-emphasis w-100 py-3 fs-5"
                @click="closeOffcanvas"
              >
                <UserAvatarComponent
                  :user="authStore.user"
                  :width="24"
                  :height="24"
                  :alignTop="2"
                />
                <span class="ms-2">{{ $t('navbarComponent.profile') }}</span>
              </router-link>
            </li>
            <li class="nav-item">
              <hr />
            </li>
            <li>
              <a class="nav-link link-body-emphasis w-100 py-3 fs-5" href="#" @click="handleLogout">
                <font-awesome-icon :icon="['fas', 'fa-sign-out-alt']" />
                <span class="ms-2">{{ $t('navbarComponent.logout') }}</span>
              </a>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </nav>
  <FooterComponent v-else />
</template>

<script>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
// Importing the i18n
import { useI18n } from 'vue-i18n'
// import the stores
import { useAuthStore } from '@/stores/authStore'
// Import the components
import FooterComponent from '@/components/FooterComponent.vue'
import UserAvatarComponent from '@/components/Users/UserAvatarComponent.vue'
// Import Notivue push
import { push } from 'notivue'

export default {
  components: {
    UserAvatarComponent,
    FooterComponent
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

    function closeOffcanvas() {
      const navbarToggler = document.querySelector('#offcanvasNavbarButton')
      const navbarCollapse = document.querySelector('#offcanvasNavbar')
      if (navbarToggler && navbarCollapse.classList.contains('show')) {
        navbarToggler.click()
      }
    }

    return {
      authStore,
      closeOffcanvas,
      handleLogout
    }
  }
}
</script>
