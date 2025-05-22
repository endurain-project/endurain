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
                <router-link :to="{ name: 'settings' }" class="nav-link link-body-emphasis w-100 py-3 fs-5">
                    <font-awesome-icon :icon="['fas', 'fa-gear']" />
                    <span class="ms-1">{{ $t("navbarComponent.settings") }}</span>
                </router-link>
            </li>
            <li class="nav-item">
                <router-link :to="{ name: 'user', params: { id: authStore.user.id } }" class="nav-link link-body-emphasis w-100 py-3 fs-5">
                    <UserAvatarComponent :user="authStore.user" :width=24 :height=24 :alignTop=2 />
                    <span class="ms-2">{{ $t("navbarComponent.profile") }}</span>
                </router-link>
            </li>
        </ul>
        <ul class="navbar-nav bg-body-tertiary rounded shadow-sm mt-3">
            <li>
                <a class="nav-link link-body-emphasis w-100 py-3 fs-5" href="#">
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

<script>
// import the stores
import { useAuthStore } from "@/stores/authStore";
// Import the components
import FooterComponent from "@/components/FooterComponent.vue";
import UserAvatarComponent from "@/components/Users/UserAvatarComponent.vue";

export default {
	components: {
		UserAvatarComponent,
		FooterComponent,
	},
	setup() {
		const authStore = useAuthStore();

		return {
			authStore,
		};
	},
};
</script>