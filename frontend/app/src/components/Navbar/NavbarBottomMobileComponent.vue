<template>
    <nav class="navbar bg-body-tertiary text-center" v-if="authStore.isAuthenticated">
        <div class="container-fluid justify-content-around">
            <router-link :to="{ name: 'home' }" class="nav-link link-body-emphasis">
                <font-awesome-icon :icon="['fas', 'fa-home']" />
                <br>
                {{ $t("navbarBottomMobileComponent.home") }}
            </router-link>
            <router-link :to="{ name: 'activities' }" class="nav-link link-body-emphasis">
                <!-- Corrected route name -->
                <font-awesome-icon :icon="['fas', 'fa-person-running']" />
                <br />
                {{ $t('navbarBottomMobileComponent.activities') }}
            </router-link>
            <router-link :to="{ name: 'gears' }" class="nav-link link-body-emphasis">
                <font-awesome-icon :icon="['fas', 'fa-bicycle']" />
                <br>
                {{ $t("navbarBottomMobileComponent.gear") }}
            </router-link>
            <router-link :to="{ name: 'summary' }" class="nav-link link-body-emphasis">
                <font-awesome-icon :icon="['fas', 'fa-calendar-alt']" />
                <br />
                {{ $t('navbarBottomMobileComponent.summary') }}
            </router-link>
            <router-link :to="{ name: 'health' }" class="nav-link link-body-emphasis">
                <font-awesome-icon :icon="['fas', 'fa-heart']" />
                <br>
                {{ $t("navbarBottomMobileComponent.health") }}
            </router-link>
            <router-link :to="{ name: 'menu' }" class="nav-link link-body-emphasis">
                <font-awesome-icon :icon="['fas', 'bars']" />
                <br>
                {{ $t("navbarBottomMobileComponent.menu") }}
            </router-link>
        </div>
    </nav>
    <FooterComponent v-else/>
</template>

<script>
import { useRouter } from "vue-router";
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
		FooterComponent,
	},
	setup() {
		const router = useRouter();
		const authStore = useAuthStore();
		const { locale, t } = useI18n();

		async function handleLogout() {
			try {
				await authStore.logoutUser(router, locale);
			} catch (error) {
				push.error(`${t("navbarComponent.errorLogout")} - ${error}`);
			}
		}

		return {
			authStore,
			handleLogout,
		};
	},
};
</script>
