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
    <FooterComponent v-else />
</template>

<script setup>
import { useAuthStore } from "@/stores/authStore";
import FooterComponent from "@/components/FooterComponent.vue";

// Composables
const authStore = useAuthStore();
</script>
