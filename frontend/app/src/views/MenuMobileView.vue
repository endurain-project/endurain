<template>
    <h1>{{ $t("navbarBottomMobileComponent.menu") }}</h1>
    <div class="d-flex flex-column text-center">
        <ul class="navbar-nav bg-body-tertiary rounded shadow-sm">
            <li class="nav-item">
                <router-link
                    :to="{ name: 'search' }"
                    class="nav-link link-body-emphasis w-100 py-3 fs-5"
                >
                    <font-awesome-icon :icon="['fas', 'magnifying-glass']" />
                    <span class="ms-1">{{ $t('navbarComponent.search') }}</span>
                </router-link>
            </li>
        </ul>
        <ul class="navbar-nav bg-body-tertiary rounded shadow-sm mt-3">
            <li class="nav-item">
                <router-link
                    :to="{ name: 'activities' }"
                    class="nav-link link-body-emphasis w-100 py-3 fs-5"
                >
                    <font-awesome-icon :icon="['fas', 'fa-person-running']" />
                    <span class="ms-1">{{ $t('navbarComponent.activities') }}</span>
                </router-link>
            </li>
            <li class="nav-item">
                <router-link
                    :to="{ name: 'summary' }"
                    class="nav-link link-body-emphasis w-100 py-3 fs-5"
                >
                    <font-awesome-icon :icon="['fas', 'fa-calendar-alt']" />
                    <span class="ms-1">{{ $t('navbarComponent.summary') }}</span>
                </router-link>
            </li>
        </ul>
        <ul class="navbar-nav bg-body-tertiary rounded shadow-sm mt-3">
            <li class="nav-item">
                <router-link :to="{ name: 'settings' }" class="nav-link link-body-emphasis w-100 py-3 fs-5">
                    <font-awesome-icon :icon="['fas', 'fa-gear']" />
                    <span class="ms-1">{{ $t("navbarComponent.settings") }}</span>
                </router-link>
            </li>
            <li class="nav-item" v-if="authStore.isAuthenticated && authStore.user.id">
                <router-link :to="{ name: 'user', params: { id: authStore.user.id } }" class="nav-link link-body-emphasis w-100 py-3 fs-5">
                    <UserAvatarComponent :user="authStore.user" :width=24 :height=24 :alignTop=2 />
                    <span class="ms-2">{{ $t("navbarComponent.profile") }}</span>
                </router-link>
            </li>
        </ul>
        <ul class="navbar-nav bg-body-tertiary rounded shadow-sm mt-3">
            <li>
                <a class="nav-link link-body-emphasis w-100 py-3 fs-5" href="#" @click="handleLogout">
                    <font-awesome-icon :icon="['fas', 'fa-sign-out-alt']" />
                    <span class="ms-2">{{ $t("navbarComponent.logout") }}</span>
                </a>
            </li>
        </ul>
        <!-- Footer pinned to bottom -->
        <div class="my-4">
            <FooterComponent :enableBackground="false" />
        </div>
    </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from "@/stores/authStore";
import { push } from 'notivue'
import FooterComponent from "@/components/FooterComponent.vue";
import UserAvatarComponent from "@/components/Users/UserAvatarComponent.vue";

const router = useRouter()
const authStore = useAuthStore();
const { locale, t } = useI18n()

async function handleLogout() {
    try {
        await authStore.logoutUser(router, locale)
    } catch (error) {
        push.error(`${t('navbarComponent.errorLogout')} - ${error}`)
    }
}
</script>